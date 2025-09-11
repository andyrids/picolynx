# Define global variables used in the Start-ProcessWithOutput function.
$global:processOutputStringGlobal = ""
$global:processErrorStringGlobal = ""

# Launch an executable and return the exitcode, output text, and error text of the process.
function Start-ProcessWithOutput
{
    # Function requires a path to an executable and an optional list of arguments
    param (
        [Parameter(Mandatory=$true)] [string]$ExecutablePath,
        [Parameter(Mandatory=$false)] [string[]]$ArgumentList
    )

    # Reset our global variables to an empty string in the event this process is called multiple times.
    $global:processOutputStringGlobal = ""
    $global:processErrorStringGlobal = ""

    # Create the Process Info object which contains details about the process.  We tell it to 
    # redirect standard output and error output which will be collected and stored in a variable.
    $ProcessStartInfoObject = New-object System.Diagnostics.ProcessStartInfo 
    $ProcessStartInfoObject.FileName = $ExecutablePath
    $ProcessStartInfoObject.CreateNoWindow = $true 
    $ProcessStartInfoObject.UseShellExecute = $false 
    $ProcessStartInfoObject.RedirectStandardOutput = $true 
    $ProcessStartInfoObject.RedirectStandardError = $true 
    
    # Add the arguments to the process info object if any were provided
    if ($ArgumentList.Count -gt 0)
    {
        $ProcessStartInfoObject.Arguments = $ArgumentList
    }

    # Create the object that will represent the process
    $Process = New-Object System.Diagnostics.Process 
    $Process.StartInfo = $ProcessStartInfoObject 

    # Define actions for the event handlers we will subscribe to in a moment.  These are checking whether
    # any data was sent by the event handler and updating the global variable if it is not null or empty.
    $ProcessOutputEventAction = { 
        if ($null -ne $EventArgs.Data -and $EventArgs.Data -ne ""){
            $global:processOutputStringGlobal += "$($EventArgs.Data)`r`n"
        }
    }
    $ProcessErrorEventAction = { 
        if ($null -ne $EventArgs.Data -and $EventArgs.Data -ne ""){
            $global:processErrorStringGlobal += "$($EventArgs.Data)`r`n"
        }
    }

    # We need to create an event handler for the Process object.  This will call the action defined above 
    # anytime that event is triggered.  We are looking for output and error data received by the process 
    # and appending the global variables with those values.
    Register-ObjectEvent -InputObject $Process -EventName "OutputDataReceived" -Action $ProcessOutputEventAction
    Register-ObjectEvent -InputObject $Process -EventName "ErrorDataReceived" -Action $ProcessErrorEventAction

    # Process starts here
    [void]$Process.Start()

    # This sets up an asyncronous task to read the console output from the process, which triggers the appropriate
    # event, which we setup handlers for just above.
    $Process.BeginErrorReadLine()
    $Process.BeginOutputReadLine()
    
    # Wait for the process to exit.  
    $Process.WaitForExit()

    # We need to wait just a moment so the async tasks that are reading the output of the process can catch
    # up.  Not having this sleep here can cause the return values to be empty or incomplete.  In my testing, 
    # it seemed like half a second was enough time to always get the data, but you may need to adjust accordingly.
    Start-Sleep -Milliseconds 500

    # Return an object that contains the exit code, output text, and error text.
    return @{
        ExitCode = $Process.ExitCode; 
        OutputString = $global:processOutputStringGlobal; 
        ErrorString = $global:processErrorStringGlobal; 
        ExitTime = $Process.ExitTime
    }
}