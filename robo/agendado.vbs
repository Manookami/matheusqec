' Roda o robô de preços SEM abrir janela (o Agendador chama este arquivo ao meio-dia).
' Antes a janela preta aparecia e, se fosse fechada, a atualização parava no meio.
Set fso = CreateObject("Scripting.FileSystemObject")
pasta = fso.GetParentFolderName(WScript.ScriptFullName)
CreateObject("WScript.Shell").Run """" & pasta & "\agendado.bat""", 0, True
