import subprocess
from types import SimpleNamespace

import pytest

from subtitleyc import gpu_compatibility as gpu
from subtitleyc.runtime_manager import RuntimeManager


@pytest.mark.parametrize(('output', 'compatible'), [
    ('NVIDIA GeForce GTX 1650, 576.57', True),
    ('NVIDIA GeForce RTX 3060 Laptop GPU, 580.97', True),
    ('NVIDIA GeForce RTX 5090, 576.57', True),
    ('NVIDIA GeForce RTX 4090, 576.56', False),
    ('NVIDIA GeForce GTX 1080 Ti, 580.97', False),
    ('NVIDIA RTX A4000, 580.97', False),
    ('NVIDIA GeForce RTX 4090, N/A', False),
    ('malformed', False),
    ('', False),
    ('NVIDIA GeForce GTX 1080, 580.97\nNVIDIA GeForce RTX 4090, 580.97', True),
])
def test_gpu_policy(output, compatible):
    assert gpu.evaluate_gpus(output)['compatible'] is compatible


def test_probe_cache_and_explicit_recheck(monkeypatch):
    calls = []
    monkeypatch.setattr(gpu.Path, 'is_file', lambda path: True)
    def run(*args, **kwargs):
        calls.append(kwargs)
        return SimpleNamespace(returncode=0, stdout='NVIDIA GeForce RTX 4090, 580.97')
    monkeypatch.setattr(gpu.subprocess, 'run', run)
    assert gpu.gpu_compatibility(refresh=True)['compatible']
    assert gpu.gpu_compatibility()['compatible']
    assert len(calls) == 1
    gpu.gpu_compatibility(refresh=True)
    assert len(calls) == 2
    assert calls[0]['timeout'] == 5


def test_detection_timeout_is_not_hardware_incompatibility(monkeypatch):
    monkeypatch.setattr(gpu.Path, 'is_file', lambda path: True)
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired('nvidia-smi', 5)
    monkeypatch.setattr(gpu.subprocess, 'run', timeout)
    result = gpu.gpu_compatibility(refresh=True)
    assert not result['compatible']
    assert 'Could not verify' in result['reason']


def test_gpu_download_rejected_before_network(tmp_path, monkeypatch):
    monkeypatch.setattr('subtitleyc.runtime_manager.gpu_compatibility', lambda **kw: {'compatible': False, 'reason': 'Update driver'})
    manager = RuntimeManager({'gpu-cuda-12.9': {}}, tmp_path)
    with pytest.raises(ValueError, match='Update driver'):
        manager.start('gpu-cuda-12.9')
    assert manager.worker is None
