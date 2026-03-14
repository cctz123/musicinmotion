"""Main entry point for the music-motion application."""

import sys
from PyQt5.QtWidgets import QApplication
from .ui.main_window import MainWindow


def main():
    """Main entry point."""
    app = QApplication(sys.argv)
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()

