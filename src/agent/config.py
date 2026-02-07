"""Supported language configurations and prerequisite definitions."""

LANGUAGE_CONFIGS = {
    "dotnet": {
        "label": ".NET/C#",
        "prerequisites": [
            {
                "command": "dotnet",
                "error": ".NET SDK is not installed.",
                "install_mac": "brew install dotnet",
                "install_win": "winget install Microsoft.DotNet.SDK.9",
            }
        ],
    },
    "python": {
        "label": "Python",
        "prerequisites": [
            {
                "command": "python3",
                "error": "Python 3 is not installed.",
                "install_mac": "brew install python",
                "install_win": "winget install Python.Python.3.12",
            }
        ],
    },
    "node": {
        "label": "Node.js",
        "prerequisites": [
            {
                "command": "node",
                "error": "Node.js is not installed.",
                "install_mac": "brew install node",
                "install_win": "winget install OpenJS.NodeJS.LTS",
            }
        ],
    },
}

VALID_LANGUAGES = list(LANGUAGE_CONFIGS.keys())
