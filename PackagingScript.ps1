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
pip install --upgrade pip
pip install pyinstaller

# Generate spec for CPU build (--onefile)
pyi-makespec gui.py --onefile --noconsole --name MarketTrackerCPU

# Move to pyinstaller/
Move-Item -Path MarketTrackerCPU.spec -Destination pyinstaller/market_tracker_cpu.spec -Force

# Generate spec for CUDA build (--onedir)
pyi-makespec gui.py --onedir --noconsole --name MarketTrackerCUDA

# Move to pyinstaller/
Move-Item -Path MarketTrackerCUDA.spec -Destination pyinstaller/market_tracker_cuda.spec -Force

# Deactivate build venv
deactivate

# Function to edit spec files to add datas
function Edit-SpecDatas {
    param (
        [string]$specPath
    )
    $content = Get-Content $specPath -Raw
    $content = $content -replace 'datas=\[\],', "datas=[('config/market.json', 'config'), ('config/item_categories.csv', 'config')],"
    Set-Content $specPath $content
}

# Edit both specs
Edit-SpecDatas -specPath "pyinstaller/market_tracker_cpu.spec"
Edit-SpecDatas -specPath "pyinstaller/market_tracker_cuda.spec"

# Build CPU-only executable
# Create and activate venv
python -m venv .venv-cpu
. .\.venv-cpu\Scripts\Activate.ps1

# Install dependencies
pip install --upgrade pip wheel setuptools
pip install -r requirements.txt
pip install torch torchvision torchaudio
pip install pyinstaller

# Build with PyInstaller
pyinstaller pyinstaller/market_tracker_cpu.spec

# Deactivate venv
deactivate

# Build CUDA-enabled executable
# Create and activate venv
python -m venv .venv-cuda
. .\.venv-cuda\Scripts\Activate.ps1

# Install dependencies
pip install --upgrade pip wheel setuptools
pip install -r requirements.txt
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu126
pip install pyinstaller

# Verify CUDA availability
try {
    python -c "import torch; assert torch.cuda.is_available()"
    Write-Output "CUDA verification passed."
} catch {
    Write-Warning "CUDA verification failed. Ensure NVIDIA drivers and CUDA toolkit are installed correctly."
    # Continue anyway, as per automation; user can check.
}

# Build with PyInstaller
pyinstaller pyinstaller/market_tracker_cuda.spec

# Deactivate venv
deactivate

# Post-build checks (automatic parts)
# Run --help for both
Write-Output "Running --help for CPU build..."
.\dist\MarketTrackerCPU.exe --help

Write-Output "Running --help for CUDA build..."
.\dist\MarketTrackerCUDA\MarketTrackerCUDA.exe --help

# Record versions for reproducibility
# Using the CUDA venv for example, but could be either
. .\.venv-cuda\Scripts\Activate.ps1
$pyinstallerVersion = pyinstaller --version
$torchVersion = pip show torch | Select-String -Pattern "Version:"
deactivate

$windowsBuild = ver

# Output to console (user can copy to release notes)
Write-Output "Reproducibility info:"
Write-Output "PyInstaller version: $pyinstallerVersion"
Write-Output "Torch info: $torchVersion"
Write-Output "Windows build: $windowsBuild"

# Save to a file
"Reproducibility info:`nPyInstaller version: $pyinstallerVersion`nTorch info: $torchVersion`nWindows build: $windowsBuild" | Out-File -FilePath release_notes.txt -Encoding utf8

# Instructions for manual parts
Write-Output "Automation complete. For smoke-testing:"
Write-Output "- Run the CPU executable on a clean machine: .\dist\MarketTrackerCPU.exe"
Write-Output "- Run the CUDA executable: .\dist\MarketTrackerCUDA\MarketTrackerCUDA.exe"
Write-Output "- Confirm debug/ artefacts, bdo_tracker.db creation, and config loading."
Write-Output "- Perform full GUI sessions and check OCR logs manually."
Write-Output "- Ship dist/MarketTrackerCPU.exe for CPU."
Write-Output "- Ship the entire dist/MarketTrackerCUDA/ directory for CUDA."