# PackagingScript.ps1
# This PowerShell script automates the executable packaging process for MarketTracker CPU and CUDA versions.
# Run this in the project root directory where gui.py and requirements.txt exist.
# Assumes prerequisites are met: Visual C++ Build Tools installed, Python 3.10-3.13 on PATH, and pip install -r requirements.txt succeeds in clean venv.
# This version creates a temporary build venv for spec generation and installs pyinstaller in each build venv.

# Create pyinstaller directory if it doesn't exist
New-Item -ItemType Directory -Force -Path pyinstaller

# Create and activate a temporary venv for spec generation
python -m venv .venv-build
. .\.venv-build\Scripts\Activate.ps1

# Install pyinstaller in the build venv
python -m pip install --upgrade --quiet pip
pip install --quiet pyinstaller

# Generate spec for CPU build (--onefile)
pyi-makespec gui.py --onefile --noconsole --name MarketTracker

# Move to pyinstaller/
Move-Item -Path MarketTracker.spec -Destination pyinstaller/market_tracker_cpu.spec -Force

# Generate spec for CUDA build (--onedir)
pyi-makespec gui.py --onedir --noconsole --name MarketTrackerCUDA

# Move to pyinstaller/
Move-Item -Path MarketTrackerCUDA.spec -Destination pyinstaller/market_tracker_cuda.spec -Force

# Deactivate build venv
deactivate

# Function to edit spec files to add datas and correct script path
function Edit-SpecDatas {
    param (
        [string]$specPath,
        [string]$mode  # 'cpu' or 'cuda'
    )
    $content = Get-Content $specPath -Raw
    $content = $content -replace 'datas=\[\],', "datas=[('../config/market.json', 'config'), ('../config/item_categories.csv', 'config'), ('../config/icon.ico', 'config')],"
    $content = $content -replace "\['gui.py'\]", "['../gui.py']"

	Set-Content $specPath $content
}

# Edit both specs
Edit-SpecDatas -specPath "pyinstaller/market_tracker_cpu.spec" -mode "cpu"
Edit-SpecDatas -specPath "pyinstaller/market_tracker_cuda.spec" -mode "cuda"

# Build CPU-only executable
# Create and activate venv
python -m venv .venv-cpu
. .\.venv-cpu\Scripts\Activate.ps1

# Install dependencies
python -m pip install --upgrade --quiet pip wheel setuptools
pip install --quiet -r requirements.txt
pip install --quiet torch torchvision torchaudio
pip install --quiet pyinstaller

# Build with PyInstaller
pyinstaller pyinstaller/market_tracker_cpu.spec --log-level WARN

# Move the CPU EXE to its own directory
New-Item -ItemType Directory -Force -Path dist/MarketTrackerCPU
Move-Item -Path dist/MarketTracker.exe -Destination dist/MarketTrackerCPU/ -Force

# Deactivate venv
deactivate

# Build CUDA-enabled executable
# Create and activate venv
python -m venv .venv-cuda
. .\.venv-cuda\Scripts\Activate.ps1

# Install dependencies
python -m pip install --upgrade --quiet pip wheel setuptools
pip install --quiet -r requirements.txt
pip install --quiet torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu129
pip install --quiet pyinstaller

# Verify CUDA availability
python -c "import torch; assert torch.cuda.is_available()"
if ($LASTEXITCODE -eq 0) {
    Write-Output "CUDA verification passed."
} else {
    Write-Error "CUDA verification failed. Ensure NVIDIA drivers and CUDA toolkit are installed correctly. Aborting CUDA build."
    deactivate
    exit 1  # Abort script
}

# Build with PyInstaller
pyinstaller pyinstaller/market_tracker_cuda.spec --log-level WARN

# Deactivate venv
deactivate

# Post-build checks (automatic parts)
# Run --help for both if they exist
if (Test-Path .\dist\MarketTrackerCPU\MarketTracker.exe) {
    Write-Output "Running --help for CPU build..."
    .\dist\MarketTracker\MarketTracker.exe --help
} else {
    Write-Warning "CPU executable not found; build may have failed."
}

if (Test-Path .\dist\MarketTrackerCUDA\MarketTrackerCUDA.exe) {
    Write-Output "Running --help for CUDA build..."
    .\dist\MarketTrackerCUDA\MarketTrackerCUDA.exe --help
} else {
    Write-Warning "CUDA executable not found; build may have failed."
}

# Record versions for reproducibility
# Using the CUDA venv for example, but could be either
. .\.venv-cuda\Scripts\Activate.ps1
$pyinstallerVersion = pyinstaller --version
$torchVersion = pip show torch | Select-String -Pattern "Version:"
deactivate

$windowsBuild = [System.Environment]::OSVersion.VersionString

# Output to console (user can copy to release notes)
Write-Output "Reproducibility info:"
Write-Output "PyInstaller version: $pyinstallerVersion"
Write-Output "Torch info: $torchVersion"
Write-Output "Windows build: $windowsBuild"

# Save to a file
"Reproducibility info:`nPyInstaller version: $pyinstallerVersion`nTorch info: $torchVersion`nWindows build: $windowsBuild" | Out-File -FilePath release_notes.txt -Encoding utf8

# Instructions for manual parts
Write-Output "Automation complete. For smoke-testing:"
Write-Output "- Run the CPU executable on a clean machine: .\dist\MarketTrackerCPU\MarketTracker.exe"
Write-Output "- Run the CUDA executable: .\dist\MarketTrackerCUDA\MarketTrackerCUDA.exe"
Write-Output "- Confirm debug/ artefacts, bdo_tracker.db creation, and config loading."
Write-Output "- Perform full GUI sessions and check OCR logs manually."
Write-Output "- Ship the entire dist/MarketTrackerCPU/ directory for CPU."
Write-Output "- Ship the entire dist/MarketTrackerCUDA/ directory for CUDA."