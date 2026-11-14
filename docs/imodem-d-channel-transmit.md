# What reaches the D-channel transmitter, and what stops it

[imodem-config-sector.md](imodem-config-sector.md) ends with this text:

> The D-channel transmit path at `0x71cb0` is never entered, and it has no
> direct callers - no far call anywhere in the image targets it, and no near
> call from any plausible segment - so it is reached through a pointer. That
> indirection is where the next look belongs.

**There is no pointer.**  That conclusion came from a search for callers of
`0x71cb0`. But `0x71cb0` is not a function. It is the middle of a function.  The
body starts at `0x71cb4`, and the function entry is **`0x71c77`**. That entry has
five ordinary far callers:

```
lcall to 71c77: 62fd9, 71074, 71c49, 72dde, 72f49
```

All of them are encoded `71ac:01b7`.  One of them runs.  During a TEI Identity Request
([imodem-tei-request.md](imodem-tei-request.md)), `0x71c49` calls it and the
function is entered, 377 instructions after the request is assembled.  Thus, the code
gets to the transmitter. But the transmitter is not *permitted* to send.

## The gate

```
71c8f  or word es:[bx+0x1e], 1        ; mark the link transmit-pending
71c94  mov al, [bp+6] ; mov bx, ax    ; the interface
71c9b  cmp byte [bx-0x5ba8], 7        ; ce0:a458+interface, the layer-1 state
71ca0  je 71cb4                       ; == 7            -> transmit
71ca2  mov bx, [bp-4]
71ca5  mov ax, es:[bx+0x10]
71ca9  and ax, 0x80 ; cmp ax, 0x80
71caf  je 71cb4                       ; flag 0x80 set   -> transmit
71cb1  jmp 71d7b                      ; otherwise nothing goes out
```

There are two ways in, and in a run, neither is open:

* **The layer-1 state byte is 8, not 7.**  8 is the activated state. It is
  the value that makes the dispatch at `0x70f38` push event 6, the activation
  event, and it causes `LINE_ACTIVE Detected`.  The `== 7` arm is
  the *other* arm. State 7 is one step below, and the firmware transmits
  while the activation is still in progress.  We tested a shift of the LSR field of the model by
  one, to make F7 store 7. It does not work: the line does not
  start, and the log is empty.  Thus, 8 is correct, and this arm is
  not the arm for an activated link.
* **The transmit-permission flag is never set.**  This is `es:[bx+0x10]` bit 7, on
  the structure that the far pointer at `ce0:a448` points to.

## The flag, and the one routine that sets it

Two sites set it, `0x72bd4` and `0x732b4`, and two sites clear it.  No setter
executes in a run here.  The important one is `0x72b83`:

```
72b8b  select 0xa4            ; LIU_LMR2
72b99  read it
72ba6  or al, 2               ; set the activation-request bit
72bae  select 0xa4 ; write al ; LMR2 |= 2
72bcd  les bx, [0x138e] ; les bx, es:[bx]
72bd4  or word es:[bx+0x10], 0x80    ; and now the link may transmit
```

That is I.430 activation **requested by the terminal**: the TE asks the
LIU to drive INFO1. Immediately after this, the routine permits layer 2 to send.  It
is the missing half of the line handling. The peer of this repository activates
from the network side, and the firmware never asks from its own side.

It has exactly one caller, `0x7067f`. That caller is one arm of a command dispatch
in the layer-1 driver, and each arm of the dispatch calls a different `7234:xxxx`
routine.  Thus, the chain is:

```
<some layer-1 command>  ->  0x7067f  ->  0x72b83  ->  LMR2 |= 2
                                                  ->  transmit permitted
```

Now there is only one open question: **what sends that command.**

## What this corrects

* `0x71cb0` is not an entry point, and the code does not get to it through a pointer.  The
  transmit function is `0x71c77`, and its callers are ordinary far calls.
* "The transmit path is never entered" is not correct.  `0x71c49` enters it,
  and it returns without a send.
* [imodem-d-channel.md](imodem-d-channel.md) tells that `LIU_LMR1` is written
  once at init and never again. It concludes that there is no terminal-initiated
  activation to model.  The register to monitor is **LMR2**, not LMR1, and the
  write is `|= 2` from `0x72b83`.  It still never occurs. But now there is
  a specific routine, and its execution would be the evidence, not an
  absence.
