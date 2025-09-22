import os
import tarfile
import urllib.request
import subprocess
import sys

def download_and_extract_yamnet(dest_dir="yamnet_model"):
    url = "https://storage.googleapis.com/tfhub-modules/google/yamnet/1.tar.gz"
    tar_path = os.path.join(dest_dir, "yamnet.tar.gz")
    os.makedirs(dest_dir, exist_ok=True)
    print(f"Downloading YAMNet model from {url} ...")
    urllib.request.urlretrieve(url, tar_path)
    print("Extracting...")
    with tarfile.open(tar_path, "r:gz") as tar:
        tar.extractall(path=dest_dir)
    print("Extraction complete.")
    return os.path.join(dest_dir, "yamnet")

def convert_to_onnx(saved_model_dir, output_path="yamnet.onnx"):
    print(f"Converting {saved_model_dir} to ONNX format...")
    cmd = [sys.executable, "-m", "tf2onnx.convert", "--saved-model", saved_model_dir, "--output", output_path, "--opset", "13"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    print(result.stdout)
    if result.returncode != 0:
        print(result.stderr)
        raise RuntimeError("ONNX conversion failed.")
    print(f"ONNX model saved to {output_path}")

def main():
    dest_dir = "yamnet_model"
    onnx_output = os.path.join(os.path.dirname(__file__), "../models/yamnet.onnx")
    saved_model_dir = download_and_extract_yamnet(dest_dir)
    convert_to_onnx(saved_model_dir, onnx_output)
    print("All done! Place yamnet.onnx in your models/ directory.")

if __name__ == "__main__":
    main()
