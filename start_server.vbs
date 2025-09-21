Set WshShell = CreateObject("WScript.Shell")
WshShell.Run "cmd /c E:\TestNOPRIZ\TN\Scripts\activate.bat && python -m waitress --host=0.0.0.0 --port=8000 testing_platform.wsgi:application", 0, False
Set WshShell = Nothing