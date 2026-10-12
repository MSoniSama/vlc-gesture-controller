Set shell = CreateObject("WScript.Shell")
Set files = CreateObject("Scripting.FileSystemObject")
root = files.GetParentFolderName(WScript.ScriptFullName)
shell.CurrentDirectory = root
python = root & "\.venv\Scripts\pythonw.exe"
If files.FileExists(python) Then
    shell.Run """" & python & """ """ & root & "\main.py" & """", 0, False
End If
