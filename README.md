# AutoHotkey.py

Write AutoHotkey scripts in Python.

## Description

AutoHotkey.py provides a user-friendly API that lets the user write hotkeys and
automation scripts in Python harnessing the power of AutoHotkey. It does so by
embedding a Python DLL into the AutoHotkey process.

## Quickstart

Ensure that you have installed [Python](https://www.python.org/downloads/) 3.7
or later and [AutoHotkey](https://www.autohotkey.com/) 1.1.28 or later.

Install the package to the Python user install directory. To do that, copy and
paste the following into a PowerShell window:

```powershell
py -m pip install --user autohotkey.py
```

Write the sample code into the `playground.py` file:

```powershell
@"
import sys
import ahkpy as ahk

ahk.message_box("Hello!")

@ahk.hotkey("F1")
def bye():
    ahk.message_box("Bye!")
    sys.exit()
"@ | Out-File -Encoding utf8 playground.py
```

Finally, run the sample code:

```powershell
py -m ahkpy playground.py
```

It will show a "Hello!" message box. When the user presses <kbd>F1</kbd>, it
will show a "Bye!" message box and exit.

You can check out and run other
[examples](https://github.com/Perlence/AutoHotkey.py/tree/master/examples) and
read the [documentation](https://ahkpy.readthedocs.io/).

## Minimum Supported Versions

- AutoHotkey 1.1.28 (U32 and U64 variants)
- Python 3.7
- Windows 10, version 1511

AutoHotkey.py was tested on the following software:

- Windows 10 v2004, v20H2
- AutoHotkey v1.1.30.03, v1.1.33.02
- Python v3.7.9, v3.8.1, v3.8.6, v3.9.1

## Credits

AutoHotkey.py was greatly inspired by Aurelain's
[Exo](https://github.com/Aurelain/Exo). Thanks to Lexikos for his monumental
work on AutoHotkey. Thanks to the AutoHotkey site admins for maintaining the
lively and welcoming forums.
