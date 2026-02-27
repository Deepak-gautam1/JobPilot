@echo off
chcp 65001 > nul
set PYTHONIOENCODING=utf-8
"C:\Users\dgautam\OneDrive - Kuwait Food Company\Desktop\Codes\chinpeerapat-jobspy\venv\Scripts\python.exe" -u "C:\Users\dgautam\OneDrive - Kuwait Food Company\Desktop\Codes\chinpeerapat-jobspy\job_alert.py" >> "C:\Users\dgautam\OneDrive - Kuwait Food Company\Desktop\Codes\chinpeerapat-jobspy\job_alert_log.txt" 2>&1
exit