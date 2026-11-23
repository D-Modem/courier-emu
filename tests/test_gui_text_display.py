"""Exercise the actual browser renderer without changing console transport bytes."""
import json
from pathlib import Path
import re
import shutil
import subprocess

import pytest


@pytest.mark.parametrize('text', [
    'AT\r\nOK\r\n',
    ''.join(chr(c | ((c.bit_count() & 1) << 7))
            for c in b'CONNECT 9600/ARQ\r\nPARITY=E WORDLEN=7\r\nOK\r\n'),
    ''.join(chr(c) for c in range(256)),
])
def test_browser_text_display_strips_parity_only_when_selected(text):
    node = shutil.which('node')
    if node is None:
        pytest.skip('optional Node runtime is needed to test the browser JavaScript')
    html = (Path(__file__).resolve().parents[1] / 'courier_emu/gui.html').read_text()
    script = html.split('<script>', 1)[1].split('</script>', 1)[0]
    renderer = re.search(r'^function terminalText\([^\n]+', script, re.MULTILINE).group()
    framing_options = re.search(r'<select id="framing">(.*?)</select>', html).group(1)
    default_framing = re.search(r'<option value="([^"]+)" selected>', framing_options).group(1)
    assert default_framing == '8bit'
    harness = '''const vm=require('vm'),fs=require('fs');
const data=JSON.parse(fs.readFileSync(0,'utf8'));
new vm.Script(data.script); // also syntax-check the entire browser program
const context={text:data.text,$:()=>({value:data.defaultFraming})};
const result=vm.runInNewContext(data.renderer+`;
JSON.stringify({seven:terminalText(text,'7bit'),eight:terminalText(text,'8bit'),
               defaultView:terminalText(text),original:text})`,context);
process.stdout.write(result);
'''
    result = subprocess.run([node, '-e', harness], input=json.dumps({
        'text': text, 'script': script, 'renderer': renderer, 'defaultFraming': default_framing,
    }), text=True, capture_output=True, timeout=10)
    assert result.returncode == 0, result.stderr
    rendered = json.loads(result.stdout)
    assert rendered['seven'] == ''.join(chr(ord(c) & 0x7f) for c in text)
    assert rendered['defaultView'] == text
    assert rendered['eight'] == text
    assert rendered['original'] == text
    # Both live rendering and transcript export must use the same conversion.
    assert 't.textContent=terminalText(output.slice(hidden))' in script
    assert 'new Blob([terminalText(output)]' in script
