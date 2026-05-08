@echo off
REM install_requirements.bat - install Python requirements into nova_env
if not exist "nova_env\Scripts\activate.bat" (
  echo Virtual environment not found at nova_env\Scripts\activate.bat
  echo Create the venv or adjust this script to your env.
  exit /b 1
)
call nova_env\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
echo Dependencies installed. If installation failed, check the output above.
pause
