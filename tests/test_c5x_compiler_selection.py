from types import SimpleNamespace
from pathlib import Path
import pytest
from courier_emu import dsp


@pytest.mark.parametrize('builder', ['build_library', 'build_runner'])
@pytest.mark.parametrize('cxx,expected', [(None,['c++']), ('',['c++']),
    ('clang++-19',['clang++-19']), ('ccache clang++-19',['ccache','clang++-19']),
    ('"/path with spaces/clang++"',['/path with spaces/clang++'])])
def test_explicit_cxx_is_used_without_a_shell(monkeypatch,tmp_path,builder,cxx,expected):
    monkeypatch.delenv('COURIER_C5X_LIBRARY',raising=False)
    if cxx is None:monkeypatch.delenv('CXX',raising=False)
    else:monkeypatch.setenv('CXX',cxx)
    monkeypatch.setattr(dsp,'BUILD_DIRECTORY',tmp_path)
    monkeypatch.setattr(dsp,'LIBRARY',tmp_path/'core.so')
    monkeypatch.setattr(dsp,'RUNNER',tmp_path/'core-runner')
    calls=[]
    def compile(cmd,**kwargs):
        calls.append((cmd,kwargs))
        return SimpleNamespace(returncode=0,stdout='',stderr='')
    monkeypatch.setattr(dsp.subprocess,'run',compile)
    result=getattr(dsp,builder)(force=True)
    cmd,kwargs=calls[0]
    assert cmd[:len(expected)]==expected
    assert cmd[len(expected)]=='-std=c++17'
    assert '-O3' in cmd
    assert cmd[-2:]==['-o',str(result)]
    assert 'shell' not in kwargs


def test_prebuilt_override_does_not_recompile_for_cxx(monkeypatch):
    monkeypatch.setenv('COURIER_C5X_LIBRARY','/explicit/core.so')
    monkeypatch.setenv('CXX','clang++-19')
    def unexpected(*args,**kwargs):raise AssertionError('recompiled explicit library')
    monkeypatch.setattr(dsp.subprocess,'run',unexpected)
    assert dsp.build_library(force=True)==Path('/explicit/core.so')
