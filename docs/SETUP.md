# Setup Guide (Mac)

This is the one-time setup. Both of you should do this on your own laptops.

## Prerequisites
- Python 3.10 or higher (`python3 --version` to check)
- VS Code installed
- Terminal access

## Steps

### 1. Create the project folder
```bash
cd ~/Desktop
mkdir practicum
cd practicum
```

### 2. Open it in VS Code
```bash
code .
```

### 3. Set up the virtual environment
In VS Code's terminal (View → Terminal):
```bash
python3 -m venv venv
source venv/bin/activate
```

Your prompt should now start with `(venv)`.

### 4. Put the files in place
Your folder should look like this:
```
practicum/
├── README.md
├── SETUP.md                    (this file)
├── demo_schema.py
├── venv/                       (don't touch — created automatically)
└── pipeline/
    ├── __init__.py             (empty file)
    └── schema.py
```

### 5. Verify it works
With the virtual environment still active:
```bash
python demo_schema.py
```

You should see output like:
```
Ground truth:
  reentrance_1: ['reentrancy']

Slither prediction:
  reentrance_1: ['reentrancy', 'timestamp_dependency']
  runtime: 2.4s
```

If you see that, you're done with Phase 0 setup.

## Every time you come back to work

Open Terminal, then:
```bash
cd ~/Desktop/practicum
source venv/bin/activate
code .
```

That's it.

## Troubleshooting

**`code: command not found`**
In VS Code: Cmd+Shift+P → type "shell command" → "Install 'code' command in PATH"

**`python3: command not found`**
Install Python from python.org or via Homebrew: `brew install python3`

**`ModuleNotFoundError: No module named 'pipeline'`**
You're running the script from the wrong folder. Make sure your terminal is in the `practicum/` folder, not `pipeline/`.
