/* Apple A1082 hardware-only backend. No v90modem datapump is linked.
 * Reuse its CoreAudio inventory and permission utilities; USB register protocol
 * follows tools/apple_usb_modem_coupler.m (Motorola SM56 / Si3056).
 * Build via tools/build_apple_line.py, with the sibling v90modem checkout.
 */
#define main apple_audio_tool_main
#include "apple_usb_modem_audio.m"
#undef main
#include "apple_modem_line.h"
#include <libusb.h>
#include <stdatomic.h>
#include <signal.h>
#include <sys/socket.h>
#include <poll.h>
#include <unistd.h>
#include <errno.h>
#include <time.h>
#include <inttypes.h>
#include <pthread.h>

#define CAP 8192u
#define SLICE 4096u
static int16_t rxq[CAP], txq[CAP], capture_buf[SLICE];
static _Atomic unsigned rr, rw, tr, tw, gaps, overflows, failed, active_line, active_gaps, closing_line;
/* Explicit DSP-reset silence is not a missing active-stream buffer. The HAL
 * continues to clock, even while the supervisor rebuilds the DSP in Python. */
static _Atomic unsigned reset_silence, tx_discard_before;
static _Atomic uint64_t reset_silence_frames, reset_rx_discarded;
static double reset_deadline;
static unsigned idle_drops;
static _Atomic unsigned tx_low_water=CAP, rx_high_water;
typedef struct {
    double last_wall, last_sample;
    unsigned last_frames, have_sample;
    _Atomic uint64_t frames, max_gap_ns, sample_discontinuities;
} callback_clock;
static callback_clock input_clock, output_clock;
#define FLAG_HOOK 1u
#define FLAG_RESET 2u
#define RESET_TIMEOUT_SECONDS 5.0
static double monotonic_seconds(void) {
    struct timespec t; clock_gettime(CLOCK_MONOTONIC,&t);
    return (double)t.tv_sec + (double)t.tv_nsec/1e9;
}
static void observe_callback(callback_clock *clock, const AudioTimeStamp *ts, UInt32 n) {
    double now=monotonic_seconds();
    int active=atomic_load(&active_line) && !atomic_load(&reset_silence);
    atomic_fetch_add(&clock->frames,n);
    if (active && clock->last_wall) {
        uint64_t gap=(uint64_t)((now-clock->last_wall)*1e9);
        if (gap>atomic_load(&clock->max_gap_ns)) atomic_store(&clock->max_gap_ns,gap);
    }
    clock->last_wall=now;
    if (ts && (ts->mFlags&kAudioTimeStampSampleTimeValid)) {
        if (active && clock->have_sample
            && fabs(ts->mSampleTime-clock->last_sample-clock->last_frames)>.5)
            atomic_fetch_add(&clock->sample_discontinuities,1);
        clock->last_sample=ts->mSampleTime;
        clock->last_frames=n;
        clock->have_sample=1;
    } else clock->have_sample=0;
}
static int reset_watchdog(void) {
    if (atomic_load(&reset_silence) && atomic_load(&active_line)
        && reset_deadline && monotonic_seconds()>reset_deadline) {
        fprintf(stderr,"[apple-line] DSP reset exceeded %.0f seconds; releasing line\n",RESET_TIMEOUT_SECONDS);
        atomic_store(&failed,1);
        return -1;
    }
    return 0;
}
static UInt32 io_block = 512;
static AudioObjectID resized_audio = kAudioObjectUnknown;
static UInt32 original_io_block;
static UInt32 requested_io_block;
static volatile sig_atomic_t stopping;
static libusb_device_handle *usb;
static int original_hook = -1, protection = -1;
static int notification_interface;
static unsigned overload_notice;
static void line_notification(const unsigned char *data, int count) {
    if (count>=2 && data[0]==0xa1 && data[1]==0x07) overload_notice=1;
}
static _Atomic int current_hook;
/* Experimental monitor: USB transactions remain serialized, but ordinary
 * status reads must not occupy the PCM producer's output deadline. */
static int async_status_enabled, status_worker_started;
static pthread_t status_worker;
static pthread_mutex_t status_usb_mutex=PTHREAD_MUTEX_INITIALIZER;
static _Atomic unsigned status_stop, status_pending, status_ring, status_polls_completed;
static void stop_signal(int sig) { (void)sig; stopping = 1; }

static double max_active_register_ms, max_active_status_ms;
static int slowest_active_register=-1;
/* Memory-only transport_selftest injection; NULL in every hardware mode. */
static int (*test_register_read)(unsigned char);
static int (*test_register_write)(unsigned char,unsigned char);
static int reg_get_raw(unsigned char reg) {
    unsigned char cmd[] = {0x80, reg, 0}, result[8], notification[16];
    if (libusb_control_transfer(usb,0x21,0,0,1,cmd,3,1000) != 3) return -1;
    /* Match the sibling hardware transport's RESPONSE_AVAILABLE barrier.
     * The notification endpoint is separate from the HAL audio streams. */
    if (notification_interface) {
        int count=0;
        int rc=libusb_interrupt_transfer(usb,0x81,notification,sizeof notification,&count,300);
        line_notification(notification,count);
        if (rc && rc!=LIBUSB_ERROR_TIMEOUT) return -1;
    }
    for (int i=0; i<10; i++) {
        int n=libusb_control_transfer(usb,0xa1,1,0,1,result,sizeof result,1000);
        if (n>0) return result[0];
        if (n<0) return -1;
        usleep(2000);
    }
    return -1;
}
static int reg_get(unsigned char reg) {
    if (test_register_read) return test_register_read(reg);
    int active=atomic_load(&active_line) && !atomic_load(&reset_silence);
    double start=monotonic_seconds();
    int result=reg_get_raw(reg);
    double elapsed=(monotonic_seconds()-start)*1000;
    if (active && elapsed>max_active_register_ms) {
        max_active_register_ms=elapsed;
        slowest_active_register=reg;
    }
    return result;
}
static int reg_put(unsigned char reg, unsigned char value) {
    if (test_register_write) return test_register_write(reg,value);
    unsigned char cmd[] = {0, reg, value};
    return libusb_control_transfer(usb,0x21,0,0,1,cmd,3,1000)==3 ? 0 : -1;
}
static int has_loop_current(int status) {
    return status>=0 && (status&0x40) && (status&31)>0 && (status&31)<31;
}
static int firmware_hook_protocol, firmware_hook_attempted;
static int (*test_hook_transfer)(uint8_t,uint8_t,uint16_t,uint16_t,unsigned char *,uint16_t,unsigned);
static int hook_command(int off) {
    /* Original x86 USmSerial FUN_9c813 -> IOCTL 22009c -> utlamot
     * FUN_1316a: CLASS_INTERFACE OUT, request 11, value 0/1, index 0,
     * zero data. This is not the raw DAA register-5 command. */
    int rc=test_hook_transfer
        ? test_hook_transfer(0x21,0x11,off,0,NULL,0,1000)
        : libusb_control_transfer(usb,0x21,0x11,off,0,NULL,0,1000);
    return rc==0 ? 0 : -1;
}
static int release_hook(int value) {
    int rc=reg_put(5,value & ~1);
    if (firmware_hook_attempted) {
        if (hook_command(0)<0) rc=-1;
        /* The firmware command may also change monitor mode. */
        if (reg_put(5,value & ~1)<0) rc=-1;
        firmware_hook_attempted=0;
    }
    return rc;
}
typedef struct {
    const char *stage;
    int status, auxiliary, settling_poll;
    unsigned notification;
    double elapsed_ms, rearmed_ms, hook_written_ms, hook_confirmed_ms;
    int prearm_status, prearm_auxiliary;
} hook_transition;
static hook_transition last_hook_transition;
static int hook_set(int off) {
    last_hook_transition=(hook_transition){"initial-read",-1,-1,-1,0,0,-1,-1,-1,-1,-1};
    int v=reg_get(5), p=off ? reg_get(17) : -1;
    if (v<0 || (off && p<0)) return -1;
    const char *stage="protection-disarm";
    double requested=monotonic_seconds(), rearmed=0, hook_written=0, hook_confirmed=0;
    int last_status=-1, last_aux=-1, settling_poll=-1, prearm_status=-1, prearm_aux=-1;
    if (off) {
        protection=p;
        if (stopping) goto abort_seizure;
        if (!(p&8)) { stage="protection-disabled"; goto abort_seizure; }
        if (!firmware_hook_protocol && reg_put(17,p & ~8)<0) goto abort_seizure;
        int actual=reg_get(17);
        if (actual<0 || (!!(actual&8)!=!!firmware_hook_protocol)) goto abort_seizure;
        /* Match the sibling's pre-seizure read sequence as well as its OH
         * barrier. Register acknowledgement need not mean the isolated
         * line-side transition has already settled. */
        int before_aux=reg_get(19), before_current=reg_get(12);
        int termination=reg_get(26), counter=reg_get(31);
        fprintf(stderr,"[apple-line] seizure precheck OPE=%02x aux=%02x current=%02x termination=%02x counter=%02x\n",actual,before_aux,before_current,termination,counter);
        stage="precheck";
        if (before_aux<0 || before_current<0 || termination<0 || counter<0 || overload_notice || stopping) goto abort_seizure;
    }
    stage="hook-write-readback";
    v=(v|8)&~1;
    if (off) v|=1;
    if (firmware_hook_protocol && (off || firmware_hook_attempted)) {
        stage="firmware-hook-command";
        if (off) {
            firmware_hook_attempted=1;
            if (hook_command(1)<0) goto abort_seizure;
        } else if (release_hook(v)<0) goto abort_seizure;
    } else if (reg_put(5,v)<0) goto abort_seizure;
    hook_written=monotonic_seconds();
    int actual=reg_get(5);
    if (actual<0 || (actual&1)!=off) goto abort_seizure;
    hook_confirmed=monotonic_seconds();
    if (off) {
      if (!firmware_hook_protocol) {
        stage="protection-rearm";
        usleep(25000);
        if (stopping) goto abort_seizure;
        /* OH readback acknowledges a command, not a conducting physical loop.
         * Validate the line once before re-arming OPE. Never extend the
         * disarmed interval with a retry/sleep loop: absent/invalid/overload
         * current releases immediately. Keep all post-arm guards below. */
        stage="prearm-current";
        last_status=prearm_status=reg_get(12);
        if (!has_loop_current(last_status) || stopping) goto abort_seizure;
        stage="prearm-auxiliary";
        last_aux=prearm_aux=reg_get(19);
        apple_modem_line_t prearm={v,last_status,-1,-1,last_aux};
        if (last_aux<0 || apple_line_overcurrent(&prearm) || overload_notice || stopping) goto abort_seizure;
        stage="protection-rearm";
        if (reg_put(17,p)<0) goto abort_seizure;
        rearmed=monotonic_seconds();
      }
        stage="loop-current";
        /* Isolation-link validity is not a powered analogue loop. A floating
         * lead can deliver full-rail ADC data which the DC blocker hides.
         * Allow seizure to settle, then refuse to dial without loop current. */
        double deadline=monotonic_seconds()+0.25;
        int status;
        do {
            if (stopping) goto abort_seizure;
            status=reg_get(12);
            last_status=status;
            if (overload_notice) {
                fprintf(stderr,"[apple-line] overload notification during seizure; releasing\n");
                goto abort_seizure;
            }
            if (has_loop_current(status)) break;
            if (status<0 || !(status&0x40) || (status&31)==31) goto abort_seizure;
            usleep(10000);
        } while (monotonic_seconds()<deadline);
        if (!has_loop_current(status)) {
            fprintf(stderr,"[apple-line] no off-hook loop current (status=%02x); check phone lead / powered FXS port\n",status);
            goto abort_seizure;
        }
    }
    if (off) {
        /* Original transport guards the complete 500 ms settling interval.
         * Never start audio/dialing after only the first nonzero current. */
        stage="settling";
        for (int i=0;i<10;i++) {
            usleep(50000);
            if (stopping) goto abort_seizure;
            int status=reg_get(12), aux=reg_get(19);
            last_status=status; last_aux=aux; settling_poll=i;
            apple_modem_line_t check={v,status,-1,-1,aux};
            if (!apple_line_valid(&check) || aux<0 || apple_line_overcurrent(&check) || overload_notice
                || (i==9 && !has_loop_current(status))) {
                fprintf(stderr,"[apple-line] seizure settling failed (status=%02x aux=%02x notification=%u); releasing\n",status,aux,overload_notice);
                goto abort_seizure;
            }
        }
    }
    if (off && firmware_hook_protocol) {
        stage="firmware-protection-readback";
        int after=reg_get(17);
        if (after<0 || !(after&8) || stopping) goto abort_seizure;
    }
    current_hook=off;
    last_hook_transition=(hook_transition){"complete",last_status,last_aux,settling_poll,
        overload_notice,(monotonic_seconds()-requested)*1000,
        rearmed ? (rearmed-requested)*1000 : -1,
        hook_written ? (hook_written-requested)*1000 : -1,
        hook_confirmed ? (hook_confirmed-requested)*1000 : -1,prearm_status,prearm_aux};
    fprintf(stderr,"[apple-line] %s\n",off ? "off-hook" : "on-hook");
    if (off) fprintf(stderr,"[apple-line] seizure timing hook_written_ms=%.3f hook_confirmed_ms=%.3f rearmed_ms=%.3f elapsed_ms=%.3f prearm_status=%d prearm_aux=%d\n",
        last_hook_transition.hook_written_ms,last_hook_transition.hook_confirmed_ms,
        last_hook_transition.rearmed_ms,last_hook_transition.elapsed_ms,prearm_status,prearm_aux);
    return 0;
abort_seizure:
    /* Do not leave the hook asserted while CoreAudio is being torn down.
     * Release first; diagnostics/readbacks must not delay the release write.
     * cleanup() remains an independent second release attempt on every exit. */
    {
        last_hook_transition=(hook_transition){stage,last_status,last_aux,settling_poll,
            overload_notice,(monotonic_seconds()-requested)*1000,
            rearmed ? (rearmed-requested)*1000 : -1,
            hook_written ? (hook_written-requested)*1000 : -1,
            hook_confirmed ? (hook_confirmed-requested)*1000 : -1,prearm_status,prearm_aux};
        int released=release_hook(v);
        int restored=p>=0 ? reg_put(17,p) : 0;
        int hook_after=reg_get(5);
        int protection_after=p>=0 ? reg_get(17) : -1;
        current_hook=0;
        fprintf(stderr,"[apple-line] hook transition failed stage=%s off=%d status=%d aux=%d poll=%d notification=%u elapsed_ms=%.3f rearmed_ms=%.3f hook_written_ms=%.3f hook_confirmed_ms=%.3f prearm_status=%d prearm_aux=%d release_verified=%d protection_restored=%d\n",
            stage,off,last_status,last_aux,settling_poll,overload_notice,
            (monotonic_seconds()-requested)*1000,
            rearmed ? (rearmed-requested)*1000 : -1,
            last_hook_transition.hook_written_ms,last_hook_transition.hook_confirmed_ms,prearm_status,prearm_aux,
            released>=0 && hook_after>=0 && !(hook_after&1),
            p<0 || (restored>=0 && protection_after>=0 && (protection_after&8)==(p&8)));
    }
    return -1;
}
static int poll_line_status(unsigned off, unsigned request, int priming, unsigned *ring) {
    int active=atomic_load(&active_line) && !atomic_load(&reset_silence);
    double start=monotonic_seconds();
    int hook=reg_get(5), status=reg_get(12), aux=reg_get(19);
    apple_modem_line_t s={hook,status,-1,-1,aux};
    if (active) {
        double elapsed=(monotonic_seconds()-start)*1000;
        if (elapsed>max_active_status_ms) max_active_status_ms=elapsed;
    }
    if (!apple_line_valid(&s) || aux<0 || apple_line_overcurrent(&s) || (off && overload_notice)) {
        fprintf(stderr,"[apple-line] invalid line status / overload (hook=%d status=%d aux=%d); releasing\n",hook,status,aux);
        return -1;
    }
    *ring=!!(hook&0x60);
    if (request==0 || priming)
        fprintf(stderr,"[apple-line] line hook=%02x status=%02x aux=%02x sense=%d\n",hook,status,aux,reg_get(29));
    return 0;
}
static void *status_worker_main(void *unused) {
    (void)unused;
    while (!atomic_load(&status_stop) && !atomic_load(&failed)) {
        if (!atomic_exchange(&status_pending,0)) { usleep(1000); continue; }
        pthread_mutex_lock(&status_usb_mutex);
        if (!atomic_load(&status_stop) && !atomic_load(&failed)) {
            unsigned ring=0;
            if (poll_line_status(atomic_load(&current_hook),1,0,&ring)<0) {
                /* Release immediately, before any additional diagnostic read.
                 * HAL sees failed first and emits silence even if the producer
                 * was already publishing an older PCM request. */
                atomic_store(&failed,1);
                atomic_store(&active_line,0);
                if (release_hook(original_hook>=0 ? original_hook : 8)==0)
                    atomic_store(&current_hook,0);
            } else atomic_store(&status_ring,ring);
            atomic_fetch_add(&status_polls_completed,1);
        }
        pthread_mutex_unlock(&status_usb_mutex);
    }
    return NULL;
}
static int status_monitor_start(void) {
    if (!async_status_enabled) return 0;
    atomic_store(&status_stop,0); atomic_store(&status_pending,0);
    atomic_store(&status_ring,0); atomic_store(&status_polls_completed,0);
    int error=pthread_create(&status_worker,NULL,status_worker_main,NULL);
    if (error) {
        fprintf(stderr,"[apple-line] cannot start USB status monitor: %s\n",strerror(error));
        return -1;
    }
    status_worker_started=1;
    fprintf(stderr,"[apple-line] asynchronous USB status monitor enabled\n");
    return 0;
}
static void status_monitor_stop(void) {
    if (!status_worker_started) return;
    atomic_store(&status_stop,1);
    pthread_join(status_worker,NULL);
    status_worker_started=0;
}
static int guarded_status_poll(unsigned off,unsigned request,int priming,unsigned *ring) {
    pthread_mutex_lock(&status_usb_mutex);
    int result=atomic_load(&failed) ? -1 : poll_line_status(off,request,priming,ring);
    if (!result) atomic_store(&status_ring,*ring);
    pthread_mutex_unlock(&status_usb_mutex);
    return result;
}
static int service_line_status(unsigned off,unsigned request,int priming,unsigned n,unsigned *ring) {
    if (async_status_enabled && n && !priming) {
        if (atomic_load(&failed)) return -1;
        atomic_store(&status_pending,1);
        *ring=atomic_load(&status_ring);
        return 0;
    }
    return guarded_status_poll(off,request,priming,ring);
}
static void cleanup(void) {
    /* No control transfer may outlive the USB handle or race final release. */
    atomic_store(&closing_line,1); atomic_store(&active_line,0);
    status_monitor_stop();
    if (usb) {
        /* Physical release precedes audio teardown and HAL-size restoration. */
        if (original_hook>=0) {
            if (release_hook(original_hook)<0 || (reg_get(5)&1))
                fprintf(stderr,"[apple-line] WARNING: cannot verify hook release; unplug modem\n");
            else fprintf(stderr,"[apple-line] verified on-hook at shutdown\n");
        }
        if (protection>=0) reg_put(17,protection);
    }
    if (au) { AudioOutputUnitStop(au); AudioUnitUninitialize(au); AudioComponentInstanceDispose(au); au=NULL; }
    if (resized_audio!=kAudioObjectUnknown) {
        AudioObjectPropertyAddress p={kAudioDevicePropertyBufferFrameSize,kAudioObjectPropertyScopeGlobal,kAudioObjectPropertyElementMain};
        if (AudioObjectSetPropertyData(resized_audio,&p,0,NULL,sizeof original_io_block,&original_io_block))
            fprintf(stderr,"[apple-line] WARNING: could not restore original audio block size\n");
        resized_audio=kAudioObjectUnknown;
    }
    if (usb) {
        if (notification_interface) libusb_release_interface(usb,0);
        notification_interface=0;
        libusb_release_interface(usb,1);
        libusb_close(usb); usb=NULL;
    }
    libusb_exit(NULL);
}
static int usb_start(void) {
    if (libusb_init(NULL)<0) return -1;
    libusb_device **list;
    ssize_t n=libusb_get_device_list(NULL,&list);
    int matches=0;
    const char *want=getenv("APPLE_MODEM_ADDR");
    for (ssize_t i=0;i<n;i++) {
        struct libusb_device_descriptor d;
        char addr[32];
        if (libusb_get_device_descriptor(list[i],&d)<0 || d.idVendor!=0x05ac || d.idProduct!=0x1401) continue;
        snprintf(addr,sizeof addr,"%u:%u",libusb_get_bus_number(list[i]),libusb_get_device_address(list[i]));
        if (want && strcmp(addr,want)) continue;
        matches++;
        if (!usb && libusb_open(list[i],&usb)<0) usb=NULL;
    }
    if (n>=0) libusb_free_device_list(list,1);
    if (matches!=1 || !usb) {
        fprintf(stderr,"[apple-line] need exactly one selected 05ac:1401 (found %d); set APPLE_MODEM_ADDR\n",matches);
        return -1;
    }
    int cfg=0, usb_rc=libusb_get_configuration(usb,&cfg);
    if (usb_rc<0) {
        fprintf(stderr,"[apple-line] cannot read USB configuration: %s\n",libusb_error_name(usb_rc)); return -1;
    }
    if (cfg!=1 && (usb_rc=libusb_set_configuration(usb,1))<0) {
        fprintf(stderr,"[apple-line] cannot set USB configuration 1: %s\n",libusb_error_name(usb_rc)); return -1;
    }
    usb_rc=libusb_claim_interface(usb,1);
    if (usb_rc<0) {
        fprintf(stderr,"[apple-line] cannot claim command interface 1: %s (another process may own the modem)\n",libusb_error_name(usb_rc)); return -1;
    }
    notification_interface=libusb_claim_interface(usb,0)==0;
    if (!notification_interface)
        fprintf(stderr,"[apple-line] notification interface unavailable; using control-response polling\n");
    else fprintf(stderr,"[apple-line] CDC completion/overload notifications enabled\n");
    fprintf(stderr,"[apple-line] hook protocol %s\n",firmware_hook_protocol ? "firmware" : "register (diagnostic)");
    original_hook=reg_get(5);
    if (original_hook<0 || (original_hook&1)) {
        fprintf(stderr,"[apple-line] refusing an unreadable or already off-hook device\n");
        original_hook=-1; return -1;
    }
    return hook_set(0);
}
static OSStatus live_input(void *ref, AudioUnitRenderActionFlags *flags,
                          const AudioTimeStamp *ts, UInt32 bus, UInt32 n,
                          AudioBufferList *unused) {
    (void)ref; (void)unused;
    if (n>SLICE) { atomic_store(&failed,1); return kAudio_ParamError; }
    observe_callback(&input_clock,ts,n);
    AudioBufferList b={.mNumberBuffers=1,.mBuffers={{1,n*2,capture_buf}}};
    OSStatus rc=AudioUnitRender(au,flags,ts,bus,n,&b);
    if (rc) { atomic_store(&failed,1); return rc; }
    if (atomic_load(&reset_silence)) {
        atomic_fetch_add(&reset_rx_discarded,n);
        return noErr;
    }
    unsigned w=atomic_load(&rw), r=atomic_load(&rr);
    if (atomic_load(&active_line) && w-r+n>atomic_load(&rx_high_water))
        atomic_store(&rx_high_water,w-r+n);
    if (w-r+n>CAP) {
        if (atomic_load(&active_line)) { atomic_fetch_add(&overflows,n); atomic_store(&failed,1); }
        return noErr;
    }
    for (unsigned i=0;i<n;i++) rxq[(w+i)%CAP]=capture_buf[i];
    atomic_store(&rw,w+n);
    return noErr;
}
static OSStatus live_output(void *ref, AudioUnitRenderActionFlags *flags,
                           const AudioTimeStamp *ts, UInt32 bus, UInt32 n,
                           AudioBufferList *io) {
    (void)ref; (void)flags; (void)ts; (void)bus;
    int16_t *out=io->mBuffers[0].mData;
    observe_callback(&output_clock,ts,n);
    if (atomic_load(&failed) || atomic_load(&closing_line)) { memset(out,0,n*2); return noErr; }
    /* Read the publication flag BEFORE queue indices. A producer publishes
     * primed PCM before clearing reset_silence. Reading tw first can combine
     * an old empty queue with the new strict-stream flag and falsely underrun. */
    unsigned resetting=atomic_load(&reset_silence);
    unsigned r=atomic_load(&tr);
    unsigned discard=atomic_load(&tx_discard_before);
    if ((int32_t)(discard-r)>0) r=discard;
    if (resetting || atomic_load(&reset_silence)) {
        memset(out,0,n*2);
        /* Do not consume newly primed data while the producer is publishing
         * a resume; only the old generation's discard boundary is retired. */
        atomic_store(&tr,r);
        atomic_fetch_add(&reset_silence_frames,n);
        return noErr;
    }
    /* Load the producer index only after observing strict mode. Also checking
     * reset again above covers entry into reset while taking the snapshot. */
    unsigned w=atomic_load(&tw);
    if (atomic_load(&active_line) && w-r<atomic_load(&tx_low_water))
        atomic_store(&tx_low_water,w-r);
    unsigned take=w-r<n ? w-r : n;
    for (unsigned i=0;i<take;i++) out[i]=txq[(r+i)%CAP];
    memset(out+take,0,(n-take)*2);
    atomic_store(&tr,r+take);
    /* Startup/on-hook silence is expected. Count all gaps; Python reports
     * rather than hiding them or treating silence as a modem CONNECT. */
    atomic_fetch_add(&gaps,n-take);
    if (atomic_load(&active_line) && n>take) {
        atomic_fetch_add(&active_gaps,n-take);
        atomic_store(&failed,1);
    }
    return noErr;
}
#define AU_CHECK(expr) do { OSStatus rc=(expr); if (rc) { fprintf(stderr,"[apple-line] %s: %d\n",#expr,(int)rc); return -1; } } while(0)
static AudioObjectID selected_audio(void) {
    AudioObjectPropertyAddress a={kAudioHardwarePropertyDevices,kAudioObjectPropertyScopeGlobal,kAudioObjectPropertyElementMain};
    UInt32 bytes=0;
    if (AudioObjectGetPropertyDataSize(kAudioObjectSystemObject,&a,0,NULL,&bytes)) return kAudioObjectUnknown;
    AudioObjectID *devices=malloc(bytes), selected=kAudioObjectUnknown;
    if (!devices) return selected;
    unsigned matches=0;
    const char *want=getenv("APPLE_MODEM_AUDIO_UID");
    if (!AudioObjectGetPropertyData(kAudioObjectSystemObject,&a,0,NULL,&bytes,devices)) {
        for (unsigned i=0;i<bytes/sizeof(*devices);i++) {
            char *name=copy_name(devices[i],kAudioObjectPropertyName);
            char *uid=copy_name(devices[i],kAudioDevicePropertyDeviceUID);
            if (name && !strcmp(name,"Apple USB Modem") && (!want || (uid && strstr(uid,want)))) {
                matches++; selected=devices[i];
            }
            free(name); free(uid);
        }
    }
    free(devices);
    return matches==1 ? selected : kAudioObjectUnknown;
}
static int live_start_mode(double rate,int start_callbacks) {
    AVAuthorizationStatus auth=[AVCaptureDevice authorizationStatusForMediaType:AVMediaTypeAudio];
    if (auth!=AVAuthorizationStatusAuthorized) {
        fprintf(stderr,"[apple-line] microphone permission required (status %ld); grant it to the launching terminal\n",(long)auth);
        return -1;
    }
    AudioObjectID dev=kAudioObjectUnknown;
    for (int i=0;i<30 && dev==kAudioObjectUnknown;i++) { dev=selected_audio(); if (dev==kAudioObjectUnknown) usleep(100000); }
    if (dev==kAudioObjectUnknown) { fprintf(stderr,"[apple-line] need exactly one selected CoreAudio Apple USB Modem; set APPLE_MODEM_AUDIO_UID\n"); return -1; }
    AudioObjectPropertyAddress a={kAudioDevicePropertyNominalSampleRate,kAudioObjectPropertyScopeGlobal,kAudioObjectPropertyElementMain};
    Float64 got=0; UInt32 z=sizeof got, one=1, slice=SLICE;
    AU_CHECK(AudioObjectSetPropertyData(dev,&a,0,NULL,sizeof rate,&rate));
    for (int i=0;i<50;i++) {
        z=sizeof got;
        AU_CHECK(AudioObjectGetPropertyData(dev,&a,0,NULL,&z,&got));
        if (fabs(got-rate)<0.1) break;
        usleep(20000);
    }
    if (fabs(got-rate)>=0.1) return -1;
    a.mSelector=kAudioDevicePropertyBufferFrameSize;
    z=sizeof io_block;
    AU_CHECK(AudioObjectGetPropertyData(dev,&a,0,NULL,&z,&io_block));
    if (requested_io_block && requested_io_block!=io_block) {
        original_io_block=io_block;
        resized_audio=dev;
        AU_CHECK(AudioObjectSetPropertyData(dev,&a,0,NULL,sizeof requested_io_block,&requested_io_block));
        z=sizeof io_block;
        AU_CHECK(AudioObjectGetPropertyData(dev,&a,0,NULL,&z,&io_block));
        if (io_block!=requested_io_block) {
            fprintf(stderr,"[apple-line] requested HAL block %u, got %u\n",requested_io_block,io_block);
            return -1;
        }
    }
    if (!io_block || io_block>SLICE) return -1;
    AudioComponentDescription cd={kAudioUnitType_Output,kAudioUnitSubType_HALOutput,kAudioUnitManufacturer_Apple,0,0};
    AudioComponent comp=AudioComponentFindNext(NULL,&cd);
    if (!comp) return -1;
    AU_CHECK(AudioComponentInstanceNew(comp,&au));
    AU_CHECK(AudioUnitSetProperty(au,kAudioOutputUnitProperty_EnableIO,kAudioUnitScope_Input,1,&one,sizeof one));
    AU_CHECK(AudioUnitSetProperty(au,kAudioOutputUnitProperty_EnableIO,kAudioUnitScope_Output,0,&one,sizeof one));
    AU_CHECK(AudioUnitSetProperty(au,kAudioOutputUnitProperty_CurrentDevice,kAudioUnitScope_Global,0,&dev,sizeof dev));
    AudioStreamBasicDescription f={.mSampleRate=got,.mFormatID=kAudioFormatLinearPCM,
        .mFormatFlags=kAudioFormatFlagIsSignedInteger|kAudioFormatFlagIsPacked,
        .mBytesPerPacket=2,.mFramesPerPacket=1,.mBytesPerFrame=2,.mChannelsPerFrame=1,.mBitsPerChannel=16};
    AU_CHECK(AudioUnitSetProperty(au,kAudioUnitProperty_StreamFormat,kAudioUnitScope_Output,1,&f,sizeof f));
    AU_CHECK(AudioUnitSetProperty(au,kAudioUnitProperty_StreamFormat,kAudioUnitScope_Input,0,&f,sizeof f));
    AU_CHECK(AudioUnitSetProperty(au,kAudioUnitProperty_MaximumFramesPerSlice,kAudioUnitScope_Global,0,&slice,sizeof slice));
    AURenderCallbackStruct in={live_input,NULL},out={live_output,NULL};
    AU_CHECK(AudioUnitSetProperty(au,kAudioOutputUnitProperty_SetInputCallback,kAudioUnitScope_Global,0,&in,sizeof in));
    AU_CHECK(AudioUnitSetProperty(au,kAudioUnitProperty_SetRenderCallback,kAudioUnitScope_Input,0,&out,sizeof out));
    AU_CHECK(AudioUnitInitialize(au));
    if (!start_callbacks) {
        fprintf(stderr,"[apple-line] initialized PCM16 at %.0f Hz, HAL block %u frames (callbacks not started)\n",got,(unsigned)io_block);
        return 0;
    }
    /* Two actual HAL callbacks of fixed priming, never an unbounded queue.
     * A millisecond-only cushion can be shorter than one callback at 7200 Hz. */
    atomic_store(&tw,2*io_block);
    AU_CHECK(AudioOutputUnitStart(au));
    fprintf(stderr,"[apple-line] duplex PCM16 at %.0f Hz, HAL block %u frames\n",got,(unsigned)io_block);
    return 0;
}
static int live_start(double rate) { return live_start_mode(rate,1); }
static int transfer(int fd,void *buf,size_t n,int writing) {
    char *p=buf;
    while(n && !stopping && !atomic_load(&failed)) {
        if (reset_watchdog()<0) return -1;
        struct pollfd f={fd,writing ? POLLOUT : POLLIN,0};
        int rc=poll(&f,1,500);
        if (rc<0 && errno==EINTR) continue;
        if (rc<0) return -1;
        if (!rc) continue;
        ssize_t k=writing ? send(fd,p,n,0) : recv(fd,p,n,0);
        if (k<0 && errno==EINTR) continue;
        if (k<=0) return -1;
        n-=k; p+=k;
    }
    return n ? -1 : 0;
}
typedef struct {
    int hook, status, auxiliary, protection, termination, counter, sense;
} control_snapshot;
typedef struct {
    control_snapshot initial, final;
    hook_transition seizure;
    int attempted, seizure_ok, release_ok, protection_ok;
} control_trial;
static control_snapshot read_control_snapshot(void) {
    control_snapshot s;
    s.hook=reg_get(5); s.status=reg_get(12); s.auxiliary=reg_get(19);
    s.protection=reg_get(17); s.termination=reg_get(26);
    s.counter=reg_get(31); s.sense=reg_get(29);
    return s;
}
static control_trial run_control_trial(void) {
    control_trial result={0};
    result.seizure=(hook_transition){"preflight",-1,-1,-1,0,0,-1,-1,-1,-1,-1};
    result.initial=read_control_snapshot();
    control_snapshot s=result.initial;
    /* Never test with disabled protection, invalid status or an occupied hook.
     * No threshold, country, termination, counter or audio writes are made. */
    if (!stopping && s.hook>=0 && !(s.hook&1) && s.status>=0 && (s.status&0x40)
        && s.auxiliary>=0 && !(s.auxiliary&1) && s.protection>=0 && (s.protection&8)
        && s.termination>=0 && s.counter>=0 && s.sense>=0) {
        result.attempted=1;
        result.seizure_ok=hook_set(1)==0;
        result.seizure=last_hook_transition;
        /* No post-success hold or active diagnostic reads. Release as soon as
         * the ordinary guarded settling interval completes (or aborts). */
        hook_set(0);
    }
    result.final=read_control_snapshot();
    result.release_ok=result.final.hook>=0 && !(result.final.hook&1);
    result.protection_ok=s.protection>=0 && result.final.protection==s.protection
        && (result.final.protection&8);
    return result;
}
static void print_control_snapshot(control_snapshot s) {
    printf("{\"hook\":%d,\"status\":%d,\"auxiliary\":%d,\"protection\":%d,\"termination\":%d,\"counter\":%d,\"sense\":%d}",
        s.hook,s.status,s.auxiliary,s.protection,s.termination,s.counter,s.sense);
}
static int control_seizure_diagnostic(const char *audio_mode,double rate) {
    signal(SIGINT,stop_signal); signal(SIGTERM,stop_signal); signal(SIGALRM,stop_signal);
    /* Cooperative deadline, plus the existing finite USB request timeouts.
     * A signal requests release; it must not kill us with the hook asserted. */
    alarm(15);
    int ready=usb_start()==0, setup_ok=ready, audio_started=0, audio_running=0;
    int want_audio=strcmp(audio_mode,"none")!=0;
    if (setup_ok && want_audio) {
        int start_requested=strcmp(audio_mode,"initialized")!=0;
        setup_ok=live_start_mode(rate,start_requested)==0;
        audio_started=setup_ok && start_requested;
        audio_running=audio_started;
        if (setup_ok && audio_started) {
            /* Require actual duplex callbacks, not merely a successful start.
             * This is on-hook silence: active-line loss checks are not bypassed. */
            double deadline=monotonic_seconds()+1;
            while (!stopping && !atomic_load(&failed)
                && (!atomic_load(&input_clock.frames) || !atomic_load(&output_clock.frames))
                && monotonic_seconds()<deadline) usleep(1000);
            setup_ok=!stopping && !atomic_load(&failed)
                && atomic_load(&input_clock.frames) && atomic_load(&output_clock.frames);
            if (setup_ok && !strcmp(audio_mode,"stopped")) {
                setup_ok=AudioOutputUnitStop(au)==noErr;
                if (setup_ok) audio_running=0;
            }
        }
    }
    control_trial result={0};
    if (setup_ok) result=run_control_trial();
    uint64_t input_frames=atomic_load(&input_clock.frames), output_frames=atomic_load(&output_clock.frames);
    cleanup();
    alarm(0);
    printf("{\"control_only\":%s,\"hook_protocol\":\"%s\",\"audio_mode\":\"%s\",\"audio_started\":%s,\"audio_running_at_seizure\":%s,\"audio_rate\":%.0f,\"input_frames\":%" PRIu64 ",\"output_frames\":%" PRIu64 ",\"dialed\":false,\"usb_ready\":%s,\"setup_ok\":%s,\"attempted\":%s,\"seizure_ok\":%s,\"interrupted\":%s",
        want_audio?"false":"true",firmware_hook_protocol?"firmware":"register",audio_mode,audio_started?"true":"false",audio_running?"true":"false",rate,input_frames,output_frames,
        ready?"true":"false",setup_ok?"true":"false",result.attempted?"true":"false",result.seizure_ok?"true":"false",stopping?"true":"false");
    if (setup_ok) {
        printf(",\"initial\":"); print_control_snapshot(result.initial);
        printf(",\"final_before_cleanup\":"); print_control_snapshot(result.final);
        hook_transition t=result.seizure;
        printf(",\"seizure\":{\"stage\":\"%s\",\"status\":%d,\"auxiliary\":%d,\"settling_poll\":%d,\"notification\":%u,\"elapsed_ms\":%.3f,\"rearmed_ms\":%.3f,\"hook_written_ms\":%.3f,\"hook_confirmed_ms\":%.3f,\"prearm_status\":%d,\"prearm_auxiliary\":%d}",
            t.stage,t.status,t.auxiliary,t.settling_poll,t.notification,t.elapsed_ms,t.rearmed_ms,t.hook_written_ms,t.hook_confirmed_ms,t.prearm_status,t.prearm_auxiliary);
    }
    printf(",\"on_hook_verified\":%s,\"protection_verified\":%s}\n",result.release_ok?"true":"false",result.protection_ok?"true":"false");
    return setup_ok && result.attempted && result.seizure_ok && result.release_ok && result.protection_ok && !stopping ? 0 : 1;
}
static int hook_test_regs[32], hook_test_mode, hook_test_tripped;
static int hook_test_released, hook_test_reads_before_release, hook_test_disarm_writes, hook_test_raw_asserts;
static int hook_test_firmware_command(uint8_t type,uint8_t request,uint16_t off,
                                     uint16_t index,unsigned char *data,uint16_t size,unsigned timeout) {
    if (type!=0x21 || request!=0x11 || off>1 || index || data || size || timeout!=1000) return -1;
    if (off) {
        if (hook_test_mode!=22) hook_test_regs[5]|=1;
        if (hook_test_mode==24) hook_test_regs[17]&=~8;
        if (hook_test_mode==21) { hook_test_tripped=1; return -1; }
    } else hook_test_regs[5]&=~1;
    return 0;
}
static int hook_test_read(unsigned char reg) {
    if (hook_test_tripped && !hook_test_released) hook_test_reads_before_release++;
    if (hook_test_mode==22 && firmware_hook_attempted && reg==5) {
        hook_test_tripped=1; return 8;
    }
    if (hook_test_mode==24 && firmware_hook_attempted && reg==17 && !(hook_test_regs[17]&8)) {
        hook_test_tripped=1; return 4;
    }
    if (hook_test_mode==1 && reg==17 && hook_test_regs[17]==4) {
        hook_test_tripped=1; return 12; /* Disarm did not take. */
    }
    if (hook_test_mode==6 && reg==5 && (hook_test_regs[5]&1)) {
        hook_test_tripped=1; stopping=1; /* Cancellation after hook assertion. */
    }
    if (hook_test_mode==3 && reg==5 && (hook_test_regs[5]&1)) {
        hook_test_tripped=1; return 8; /* Hook write/readback mismatch. */
    }
    if (reg==12) {
        if ((hook_test_regs[5]&1) && !(hook_test_regs[17]&8)
            && (hook_test_mode==7 || hook_test_mode==8)) {
            hook_test_tripped=1;
            return hook_test_mode==7 ? 0x40 : 0x5f;
        }
        return (hook_test_regs[5]&1) ? 0x45 : 0x40;
    }
    if (reg==19) {
        if ((hook_test_regs[5]&1)
            && (((hook_test_mode==4 || hook_test_mode==23) && (hook_test_regs[17]&8))
                || (hook_test_mode==9 && !(hook_test_regs[17]&8)))) {
            hook_test_tripped=1; return 1; /* OPD during settling. */
        }
        return (hook_test_regs[5]&1) ? 0 : 2;
    }
    return hook_test_regs[reg];
}
static int hook_test_write(unsigned char reg,unsigned char value) {
    hook_test_regs[reg]=value;
    if (reg==17 && !(value&8)) hook_test_disarm_writes++;
    if (reg==5 && (value&1)) hook_test_raw_asserts++;
    if (reg==5 && !(value&1) && hook_test_tripped) hook_test_released=1;
    if (reg==5 && (value&1) && hook_test_mode==2) {
        hook_test_tripped=1; return -1; /* Error after the device took write. */
    }
    return 0;
}
static int hook_abort_selftest(void) {
    int ok=1, saved_protocol=firmware_hook_protocol;
    firmware_hook_protocol=0;
    test_register_read=hook_test_read;
    test_register_write=hook_test_write;
    for (hook_test_mode=1;hook_test_mode<=9;hook_test_mode++) {
        if (hook_test_mode==5) continue; /* Success is exercised via control trial below. */
        memset(hook_test_regs,0,sizeof hook_test_regs);
        hook_test_regs[5]=8; hook_test_regs[17]=12;
        hook_test_tripped=hook_test_released=hook_test_reads_before_release=0;
        if (hook_set(1)>=0 || !hook_test_released || hook_test_reads_before_release
            || (hook_test_regs[5]&1) || hook_test_regs[17]!=12) ok=0;
        stopping=0;
    }
    hook_test_mode=5;
    memset(hook_test_regs,0,sizeof hook_test_regs);
    hook_test_regs[5]=8; hook_test_regs[17]=12;
    hook_test_tripped=hook_test_released=hook_test_reads_before_release=0;
    control_trial trial=run_control_trial();
    if (!trial.attempted || !trial.seizure_ok || !trial.release_ok || !trial.protection_ok
        || strcmp(trial.seizure.stage,"complete") || trial.seizure.settling_poll!=9
        || trial.seizure.hook_written_ms<0
        || trial.seizure.hook_confirmed_ms<trial.seizure.hook_written_ms
        || trial.seizure.rearmed_ms<trial.seizure.hook_confirmed_ms) ok=0;
    hook_test_mode=4;
    trial=run_control_trial();
    if (!trial.attempted || trial.seizure_ok || !trial.release_ok || !trial.protection_ok
        || strcmp(trial.seizure.stage,"settling")) ok=0;
    hook_test_tripped=hook_test_released=hook_test_reads_before_release=0;
    hook_test_regs[17]=4; /* Disabled OPE must prevent a diagnostic seizure. */
    trial=run_control_trial();
    if (trial.attempted || trial.seizure_ok || trial.protection_ok || !trial.release_ok) ok=0;
    firmware_hook_protocol=1;
    test_hook_transfer=hook_test_firmware_command;
    for (hook_test_mode=20;hook_test_mode<=24;hook_test_mode++) {
        memset(hook_test_regs,0,sizeof hook_test_regs);
        hook_test_regs[5]=8; hook_test_regs[17]=12;
        hook_test_tripped=hook_test_released=hook_test_reads_before_release=hook_test_disarm_writes=hook_test_raw_asserts=0;
        trial=run_control_trial();
        if (!trial.attempted || (trial.seizure_ok!=(hook_test_mode==20))
            || !trial.release_ok || !trial.protection_ok || hook_test_reads_before_release
            || hook_test_disarm_writes || hook_test_raw_asserts || firmware_hook_attempted) ok=0;
    }
    test_hook_transfer=NULL;
    firmware_hook_protocol=saved_protocol;
    test_register_read=NULL; test_register_write=NULL;
    protection=-1;
    return ok;
}
static _Atomic unsigned monitor_test_entered,monitor_test_continue,monitor_test_overload,monitor_test_read_completed;
static int monitor_test_regs[256],monitor_test_hook_off;
static int monitor_test_read(unsigned char reg) {
    if (reg==5 && !atomic_load(&monitor_test_continue)) {
        atomic_store(&monitor_test_entered,1);
        double deadline=monotonic_seconds()+1;
        while (!atomic_load(&monitor_test_continue) && monotonic_seconds()<deadline) usleep(1000);
        atomic_store(&monitor_test_read_completed,1);
    }
    return reg==19 && atomic_load(&monitor_test_overload) ? 1 : monitor_test_regs[reg];
}
static int monitor_test_write(unsigned char reg,unsigned char value) {
    monitor_test_regs[reg]=value; return 0;
}
static int monitor_test_hook(uint8_t type,uint8_t request,uint16_t value,uint16_t index,
                             unsigned char *data,uint16_t length,unsigned timeout) {
    if (type!=0x21 || request!=0x11 || value || index || data || length || timeout!=1000) return -1;
    monitor_test_hook_off++;
    return 0;
}
static int status_monitor_selftest(void) {
    int saved_hook=original_hook, saved_current=current_hook, saved_protocol=firmware_hook_protocol;
    unsigned saved_failed=atomic_load(&failed),saved_active=atomic_load(&active_line),saved_reset=atomic_load(&reset_silence);
    int ok=1;
    memset(monitor_test_regs,0,sizeof monitor_test_regs);
    monitor_test_regs[5]=9; monitor_test_regs[12]=0x45; monitor_test_regs[17]=12;
    monitor_test_hook_off=0;
    atomic_store(&monitor_test_entered,0); atomic_store(&monitor_test_continue,0); atomic_store(&monitor_test_overload,0);
    atomic_store(&monitor_test_read_completed,0);
    test_register_read=monitor_test_read; test_register_write=monitor_test_write; test_hook_transfer=monitor_test_hook;
    original_hook=8; current_hook=1; firmware_hook_protocol=firmware_hook_attempted=1;
    atomic_store(&failed,0); atomic_store(&active_line,1); atomic_store(&reset_silence,0);
    async_status_enabled=1;
    if (status_monitor_start()<0) ok=0;
    atomic_store(&status_pending,1);
    double deadline=monotonic_seconds()+1;
    while (!atomic_load(&monitor_test_entered) && monotonic_seconds()<deadline) usleep(1000);
    if (!atomic_load(&monitor_test_entered)) ok=0;
    /* The worker is deliberately blocked in a mocked USB read. Publishing
     * PCM / requesting more polls must still complete before that read does. */
    atomic_store(&tr,0); atomic_store(&tw,8); atomic_store(&tx_discard_before,0);
    int16_t out[8]; for (int i=0;i<8;i++) txq[i]=100+i;
    AudioBufferList io={.mNumberBuffers=1,.mBuffers={{1,sizeof out,out}}};
    AudioTimeStamp ts={0}; AudioUnitRenderActionFlags flags=0;
    unsigned ring=0;
    if (service_line_status(1,1,0,8,&ring)<0 || atomic_load(&monitor_test_read_completed)) ok=0;
    live_output(NULL,&flags,&ts,0,8,&io);
    for (int i=0;i<8;i++) if (out[i]!=100+i) ok=0;
    if (atomic_load(&monitor_test_continue) || atomic_load(&failed)) ok=0;
    atomic_store(&monitor_test_continue,1);
    deadline=monotonic_seconds()+1;
    while (!atomic_load(&status_polls_completed) && monotonic_seconds()<deadline) usleep(1000);
    if (!atomic_load(&status_polls_completed)) ok=0;
    atomic_store(&monitor_test_overload,1); atomic_store(&status_pending,1);
    deadline=monotonic_seconds()+1;
    while (!atomic_load(&failed) && monotonic_seconds()<deadline) usleep(1000);
    status_monitor_stop();
    if (!atomic_load(&failed) || atomic_load(&active_line) || (monitor_test_regs[5]&1)
        || monitor_test_regs[17]!=12 || !monitor_test_hook_off || firmware_hook_attempted) ok=0;
    for (int i=0;i<8;i++) out[i]=777;
    live_output(NULL,&flags,&ts,0,8,&io);
    for (int i=0;i<8;i++) if (out[i]) ok=0;
    test_register_read=NULL; test_register_write=NULL; test_hook_transfer=NULL;
    original_hook=saved_hook; current_hook=saved_current; firmware_hook_protocol=saved_protocol;
    async_status_enabled=0;
    atomic_store(&failed,saved_failed); atomic_store(&active_line,saved_active); atomic_store(&reset_silence,saved_reset);
    return ok;
}
static int transport_selftest(void) {
#define EXPECT(x) do { if (!(x)) { fprintf(stderr,"selftest failed: %s\n",#x); return 1; } } while (0)
    EXPECT(hook_abort_selftest());
    unsigned char normal_notice[]={0xa1,0x01}, overload[]={0xa1,0x07};
    line_notification(normal_notice,sizeof normal_notice); EXPECT(!overload_notice);
    line_notification(overload,1); EXPECT(!overload_notice);
    line_notification(overload,sizeof overload); EXPECT(overload_notice);
    overload_notice=0;
    EXPECT(!has_loop_current(-1) && !has_loop_current(0x40));
    EXPECT(!has_loop_current(0x09) && !has_loop_current(0x5f));
    EXPECT(has_loop_current(0x41) && has_loop_current(0x49));
    int16_t out[8]; AudioTimeStamp ts={0}; AudioUnitRenderActionFlags flags=0;
    AudioBufferList io={.mNumberBuffers=1,.mBuffers={{1,sizeof out,out}}};
    atomic_store(&active_line,1); atomic_store(&reset_silence,1);
    txq[0]=111; txq[1]=222; atomic_store(&tw,2); atomic_store(&tx_discard_before,2);
    live_output(NULL,&flags,&ts,0,8,&io);
    for (unsigned i=0;i<8;i++) EXPECT(out[i]==0);
    EXPECT(atomic_load(&reset_silence_frames)==8 && !atomic_load(&active_gaps));
    /* A pause/resume wholly between callbacks must still discard old data,
     * but not the new PCM that was primed before clearing reset mode. */
    for (unsigned i=2;i<6;i++) txq[i]=333;
    for (unsigned i=6;i<10;i++) txq[i]=600+i;
    atomic_store(&tw,10); atomic_store(&tx_discard_before,6);
    live_output(NULL,&flags,&ts,0,8,&io);
    EXPECT(atomic_load(&tr)==6 && atomic_load(&reset_silence_frames)==16);
    atomic_store(&reset_silence,0);
    live_output(NULL,&flags,&ts,0,4,&io);
    for (unsigned i=0;i<4;i++) EXPECT(out[i]==606+(int)i);
    EXPECT(!atomic_load(&failed) && !atomic_load(&active_gaps));
    live_output(NULL,&flags,&ts,0,4,&io);
    EXPECT(atomic_load(&failed) && atomic_load(&active_gaps)==4);
    callback_clock test_clock={0};
    ts.mFlags=kAudioTimeStampSampleTimeValid; ts.mSampleTime=0;
    observe_callback(&test_clock,&ts,8);
    ts.mSampleTime=8; observe_callback(&test_clock,&ts,8);
    EXPECT(!atomic_load(&test_clock.sample_discontinuities));
    ts.mSampleTime=24; observe_callback(&test_clock,&ts,8);
    EXPECT(atomic_load(&test_clock.sample_discontinuities)==1);
    atomic_store(&failed,0); atomic_store(&reset_silence,1);
    reset_deadline=monotonic_seconds()-1;
    EXPECT(reset_watchdog()<0 && atomic_load(&failed));
    EXPECT(status_monitor_selftest());
    /* Closing is explicit, not a forgiveness path for an earlier underrun. */
    unsigned saved_gap_count=atomic_load(&active_gaps);
    atomic_store(&failed,0); atomic_store(&closing_line,1); atomic_store(&reset_silence,0);
    for (unsigned i=0;i<8;i++) out[i]=777;
    live_output(NULL,&flags,&ts,0,8,&io);
    for (unsigned i=0;i<8;i++) EXPECT(out[i]==0);
    EXPECT(atomic_load(&active_gaps)==saved_gap_count && atomic_load(&reset_silence_frames)==16);
    atomic_store(&closing_line,0); atomic_store(&failed,1); atomic_store(&reset_silence,1);
    printf("{\"reset_silence_frames\":%" PRIu64 ",\"strict_underrun_detected\":true,\"reset_watchdog_detected\":true,\"generation_flush\":true,\"hook_abort_release_verified\":true,\"control_only_trial_verified\":true,\"firmware_hook_protocol_verified\":true,\"async_status_monitor_verified\":true,\"explicit_shutdown_silence_verified\":true}\n",atomic_load(&reset_silence_frames));
    return 0;
#undef EXPECT
}
int main(int argc,char **argv) { @autoreleasepool {
    const char *hook_protocol=getenv("APPLE_LINE_HOOK_PROTOCOL");
    if (hook_protocol && strcmp(hook_protocol,"register") && strcmp(hook_protocol,"firmware")) {
        fprintf(stderr,"APPLE_LINE_HOOK_PROTOCOL must be register or firmware\n"); return 2;
    }
    /* Use the device firmware hook operation used by the original driver.
     * Raw register mode is an explicit diagnostic control, never a fallback. */
    firmware_hook_protocol=!hook_protocol || !strcmp(hook_protocol,"firmware");
    if (argc==2 && !strcmp(argv[1],"--selftest")) return transport_selftest();
    if (argc>=2 && !strcmp(argv[1],"--seizure-test")) {
        const char *mode=argc>=3 ? argv[2] : "none";
        char *end=NULL;
        double rate=argc==4 ? strtod(argv[3],&end) : 10286;
        int supported=rate==7200 || rate==8000 || rate==8229 || rate==8400 || rate==9000 || rate==9600 || rate==10286;
        if (argc>4 || (argc==4 && (!*argv[3] || *end)) || !isfinite(rate) || !supported
            || (strcmp(mode,"none") && strcmp(mode,"initialized") && strcmp(mode,"running") && strcmp(mode,"stopped"))) {
            fprintf(stderr,"usage: %s --seizure-test [none|initialized|running|stopped] [RATE]\n",argv[0]); return 2;
        }
        return control_seizure_diagnostic(mode,rate);
    }
    if (argc==2 && !strcmp(argv[1],"--audio-info")) {
        AudioObjectID dev=selected_audio();
        if (dev==kAudioObjectUnknown) return 1;
        AudioObjectPropertyAddress p={kAudioDevicePropertyBufferFrameSize,kAudioObjectPropertyScopeGlobal,kAudioObjectPropertyElementMain};
        UInt32 frames=0,z=sizeof frames;
        AU_CHECK(AudioObjectGetPropertyData(dev,&p,0,NULL,&z,&frames));
        AudioValueRange range={0}; p.mSelector=kAudioDevicePropertyBufferFrameSizeRange; z=sizeof range;
        AU_CHECK(AudioObjectGetPropertyData(dev,&p,0,NULL,&z,&range));
        printf("{\"buffer_frames\":%u,\"minimum_frames\":%.0f,\"maximum_frames\":%.0f",frames,range.mMinimum,range.mMaximum);
        for (int i=0;i<2;i++) {
            p.mScope=i ? kAudioObjectPropertyScopeOutput : kAudioObjectPropertyScopeInput;
            UInt32 latency=0,safety=0;
            p.mSelector=kAudioDevicePropertyLatency;z=sizeof latency;
            OSStatus lr=AudioObjectGetPropertyData(dev,&p,0,NULL,&z,&latency);
            p.mSelector=kAudioDevicePropertySafetyOffset;z=sizeof safety;
            OSStatus sr=AudioObjectGetPropertyData(dev,&p,0,NULL,&z,&safety);
            printf(",\"%s_latency_frames\":%u,\"%s_safety_frames\":%u,\"%s_query_error\":%d",i?"output":"input",latency,i?"output":"input",safety,i?"output":"input",(int)(lr?lr:sr));
        }
        puts("}"); return 0;
    }
    if (argc==2 && !strcmp(argv[1],"--devices")) {
        char *args[]={argv[0],"list",NULL};
        return apple_audio_tool_main(2,args);
    }
    if (argc==2 && !strcmp(argv[1],"--status")) {
        int rc=usb_start();
        if (!rc) {
            int hook=reg_get(5), status=reg_get(12), sense=reg_get(29), aux=reg_get(19);
            printf("{\"hook\":%d,\"status\":%d,\"sense\":%d,\"auxiliary\":%d,\"rx_gain_register\":%d,\"tx_gain_register\":%d,\"protection_register\":%d,\"termination_register\":%d}\n",hook,status,sense,aux,reg_get(15),reg_get(16),reg_get(17),reg_get(26));
            rc=hook<0 || status<0 || sense<0 || aux<0;
        }
        cleanup(); return rc ? 1 : 0;
    }
    if (argc!=3) { fprintf(stderr,"usage: %s FD RATE | --devices | --status | --seizure-test | --selftest\n",argv[0]); return 2; }
    const char *block=getenv("APPLE_MODEM_BUFFER_FRAMES");
    if (block && *block) {
        char *end=NULL; unsigned long value=strtoul(block,&end,10);
        if (*end || value>SLICE || (value && value<4)) return 2;
        requested_io_block=(UInt32)value;
    }
    int fd=atoi(argv[1]); double rate=atof(argv[2]);
    int supported=rate==7200 || rate==8000 || rate==8229 || rate==8400 || rate==9000 || rate==9600 || rate==10286;
    if (fd<3 || !supported) return 2;
    signal(SIGINT,stop_signal); signal(SIGTERM,stop_signal); signal(SIGPIPE,SIG_IGN);
    const char *async_status=getenv("APPLE_LINE_ASYNC_STATUS");
    if (async_status && strcmp(async_status,"0") && strcmp(async_status,"1")) {
        fprintf(stderr,"APPLE_LINE_ASYNC_STATUS must be 0 or 1\n"); return 2;
    }
    async_status_enabled=async_status && !strcmp(async_status,"1");
    int rc=1;
    if (usb_start()<0 || status_monitor_start()<0) { cleanup(); return 1; }
    /* Wire format (little-endian on macOS ARM/x86): count:u32, flags:u32,
     * count PCM16; reply count/ring/gaps/overflows:u32, count PCM16.
     * Flags: bit 0 hook, bit 1 explicit DSP-reset silence. Count zero is
     * control-only: ACK immediately, no ADC wait or codec rate required. */
    unsigned requests=0, ring=0;
    double next_status_poll=0;
    int reply_started=0;
    while (!stopping && !atomic_load(&failed)) {
        reply_started=0;
        uint32_t h[2]; int16_t samples[2048];
        if (transfer(fd,h,sizeof h,0)<0) { rc=atomic_load(&failed) ? 1 : 0; break; }
        unsigned n=h[0], flags=h[1];
        if (n>2048 || (flags & ~(FLAG_HOOK|FLAG_RESET)) || transfer(fd,samples,n*2,0)<0) break;
        unsigned off=!!(flags&FLAG_HOOK), resetting=!!(flags&FLAG_RESET);
        if (n && resetting) { fprintf(stderr,"[apple-line] reset control cannot carry DSP PCM\n"); break; }
        unsigned was_reset=atomic_load(&reset_silence);
        int hook_changed=(int)off!=current_hook;
        int priming=off && (hook_changed || (was_reset && !resetting));
        /* Mute before any USB operation. Release is not contingent on HAL
         * startup, an ADC buffer, or the guest programming a codec clock. */
        if (resetting || !off) {
            atomic_store(&reset_silence,resetting);
            atomic_store(&tx_discard_before,atomic_load(&tw));
            if (!off) atomic_store(&active_line,0);
        }
        if (!au && (n || off) && live_start(rate)<0) break;
        if ((int)off!=current_hook) {
            pthread_mutex_lock(&status_usb_mutex);
            int hook_result=atomic_load(&failed) ? -1 : hook_set(off);
            pthread_mutex_unlock(&status_usb_mutex);
            if (hook_result<0) break;
            atomic_store(&rr,atomic_load(&rw));
        }
        ring=atomic_load(&status_ring);
        if (resetting != was_reset)
            fprintf(stderr,"[apple-line] DSP reset silence %s\n",resetting ? "on" : "off");
        if (resetting && off && (!was_reset || !atomic_load(&active_line)))
            reset_deadline=monotonic_seconds()+RESET_TIMEOUT_SECONDS;
        if (!resetting || !off) reset_deadline=0;
        if (resetting || was_reset) atomic_store(&rr,atomic_load(&rw));
        if (!off) {
            /* Supervisor boot/download may pause indefinitely on-hook. Its
             * monitor hears the current line, never a stale boot-time FIFO.
             * Once seized, no samples are discarded and overflow is fatal. */
            unsigned r=atomic_load(&rr), w=atomic_load(&rw);
            if (w-r>(unsigned)(rate*.1)) {
                unsigned keep=io_block;
                idle_drops+=w-r-keep;
                atomic_store(&rr,w-keep);
            }
        }
        /* Control/seizure checks stay ahead of activation. During ordinary
         * streaming, publish the already-received TX block BEFORE slow USB
         * status reads, so those reads do not consume its output deadline. */
        unsigned request=requests++;
        int status_due=(!requested_io_block && request%10==0)
            || (requested_io_block && monotonic_seconds()>=next_status_poll);
        if (status_due) next_status_poll=monotonic_seconds()+0.2;
        if (status_due && (!n || priming) && service_line_status(off,request,priming,n,&ring)<0) break;
        if (!n) {
            if (priming && !resetting) {
                unsigned w=atomic_load(&tw), r=atomic_load(&tr);
                unsigned discard=atomic_load(&tx_discard_before);
                if ((int32_t)(discard-r)>0) r=discard;
                while (w-r<2*io_block && w-r<CAP) txq[(w++)%CAP]=0;
                atomic_store(&tw,w);
            }
            atomic_store(&active_line,off);
            atomic_store(&reset_silence,resetting);
            uint32_t reply[]={0,ring,atomic_load(&active_gaps),atomic_load(&overflows)};
            reply_started=1;
            if (transfer(fd,reply,sizeof reply,1)<0) { rc=atomic_load(&failed) ? 1 : 0; break; }
            continue;
        }
        unsigned w=atomic_load(&tw),r=atomic_load(&tr);
        unsigned discard=atomic_load(&tx_discard_before);
        if ((int32_t)(discard-r)>0) r=discard;
        if (priming) {
            unsigned target=2*io_block;
            while (w-r<target && w-r<CAP-n) txq[(w++)%CAP]=0;
        }
        if (w-r+n>CAP) { fprintf(stderr,"[apple-line] TX queue overflow\n"); break; }
        for (unsigned i=0;i<n;i++) txq[(w+i)%CAP]=off ? samples[i] : 0;
        atomic_store(&tw,w+n);
        atomic_store(&active_line,off);
        atomic_store(&reset_silence,0);
        if (status_due && !priming && service_line_status(off,request,priming,n,&ring)<0) break;
        ring=atomic_load(&status_ring);
        int waits=0;
        while (atomic_load(&rw)-atomic_load(&rr)<n && !stopping && !atomic_load(&failed) && waits++<3000) usleep(1000);
        if (stopping || atomic_load(&failed) || waits>=3000) break;
        r=atomic_load(&rr);
        for (unsigned i=0;i<n;i++) samples[i]=rxq[(r+i)%CAP];
        atomic_store(&rr,r+n);
        uint32_t reply[]={n,ring,atomic_load(&active_gaps),atomic_load(&overflows)};
        reply_started=1;
        if (transfer(fd,reply,sizeof reply,1)<0 || transfer(fd,samples,n*2,1)<0) { rc=atomic_load(&failed) ? 1 : 0; break; }
    }
    fprintf(stderr,"[apple-line] PCM stream ended: failed=%u active output gaps=%u\n",atomic_load(&failed),atomic_load(&active_gaps));
    /* Explicit EOF/cancel/fault ends the stream. Mute before joining a slow
     * USB poll or releasing the hook, not after draining the final TX cushion.
     * Already observed active failures/counters remain intact and fatal. */
    atomic_store(&closing_line,1); atomic_store(&active_line,0);
    /* A failed callback normally aborts transfer(), so its counters otherwise
     * never reach Python. Send a best-effort terminal header only if no part
     * of this request's normal reply has been emitted. Never append a header
     * inside a partially sent PCM reply. */
    if (!reply_started && atomic_load(&failed)
        && (atomic_load(&active_gaps) || atomic_load(&overflows))) {
        uint32_t reply[]={0,ring,atomic_load(&active_gaps),atomic_load(&overflows)};
        (void)send(fd,reply,sizeof reply,MSG_DONTWAIT);
    }
    status_monitor_stop();
    fprintf(stderr,"[apple-line] completed asynchronous status polls=%u\n",atomic_load(&status_polls_completed));
    fprintf(stderr,"[apple-line] stopped: active output gaps=%u, total output gaps=%u, input overflow=%u, idle discarded=%u, reset silence=%" PRIu64 ", reset RX discarded=%" PRIu64 "\n",atomic_load(&active_gaps),atomic_load(&gaps),atomic_load(&overflows),idle_drops,atomic_load(&reset_silence_frames),atomic_load(&reset_rx_discarded));
    fprintf(stderr,"[apple-line] longest active USB register read %.3f ms (register %d), complete status poll %.3f ms\n",max_active_register_ms,slowest_active_register,max_active_status_ms);
    fprintf(stderr,"[apple-line] HAL frames input=%" PRIu64 " output=%" PRIu64 ", active TX low-water=%u RX high-water=%u, callback max gap ms input=%.3f output=%.3f, sample-time discontinuities input=%" PRIu64 " output=%" PRIu64 "\n",
        atomic_load(&input_clock.frames),atomic_load(&output_clock.frames),
        atomic_load(&tx_low_water),atomic_load(&rx_high_water),
        atomic_load(&input_clock.max_gap_ns)/1e6,atomic_load(&output_clock.max_gap_ns)/1e6,
        atomic_load(&input_clock.sample_discontinuities),atomic_load(&output_clock.sample_discontinuities));
    cleanup(); return rc || atomic_load(&failed);
} }
