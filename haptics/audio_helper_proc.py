import subprocess, threading, json, sys, os, platform
from typing import Optional, Dict

class AudioHelperProc:
    def __init__(self, hint: str = ""):
        self._proc: Optional[subprocess.Popen] = None
        self._th: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._latest: Dict[str, float] = {"bodyL":0.0, "bodyR":0.0, "impact":0.0, "engine":0.0, "road":0.0}
        self._device_name: str = ""
        self._hint = hint

    def start(self) -> bool:
        exe = self._find_helper()
        if not exe:
            return False
        try:
            args = [exe]
            if self._hint:
                args.append(self._hint)
            self._proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, bufsize=1)
        except Exception:
            self._proc = None
            return False
        self._stop.clear()
        self._th = threading.Thread(target=self._reader, daemon=True)
        self._th.start()
        return True

    def _find_helper(self) -> Optional[str]:
        # Try common relative paths for Windows (exe) and macOS (Swift SPM build)
        roots = [os.path.dirname(os.path.dirname(__file__)), os.getcwd()]
        if platform.system().lower() == 'windows':
            candidates = [
                os.path.join('WindowsAudioHelper','bin','Release','net8.0','win-x64','publish','AudioHelper.exe'),
                os.path.join('WindowsAudioHelper','bin','Debug','net8.0','win-x64','publish','AudioHelper.exe'),
                os.path.join('WindowsAudioHelper','AudioHelper.exe'),
                'AudioHelper.exe',
            ]
        else:
            candidates = [
                os.path.join('MacAudioHelper','.build','release','MacAudioHelper'),
                os.path.join('MacAudioHelper','.build','debug','MacAudioHelper'),
            ]
        for root in roots:
            for rel in candidates:
                path = os.path.join(root, rel)
                if os.path.isfile(path):
                    if platform.system().lower() != 'windows':
                        try:
                            os.chmod(path, 0o755)
                        except Exception:
                            pass
                    return path
        return None

    def _reader(self):
        fp = self._proc.stdout if self._proc else None
        if not fp:
            return
        for line in fp:
            if self._stop.is_set():
                break
            try:
                obj = json.loads(line.strip())
                if isinstance(obj, dict):
                    if obj.get('status') == 'started':
                        self._device_name = str(obj.get('device',''))
                    elif 'bodyL' in obj and 'bodyR' in obj:
                        self._latest = {
                            'bodyL': float(obj.get('bodyL') or 0.0),
                            'bodyR': float(obj.get('bodyR') or 0.0),
                            'impact': float(obj.get('impact') or 0.0),
                            'engine': float(obj.get('engine') or 0.0),
                            'road': float(obj.get('road') or 0.0),
                        }
                        if obj.get('device'):
                            self._device_name = str(obj['device'])
            except Exception:
                continue

    def get(self) -> Dict[str, float]:
        return dict(self._latest)

    def device_name(self) -> str:
        return self._device_name

    def close(self):
        self._stop.set()
        try:
            if self._proc and self._proc.poll() is None:
                self._proc.terminate()
        except Exception:
            pass
