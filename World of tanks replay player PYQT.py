# Write your code here :-)
import sys
from PyQt5.QtWidgets import QApplication, QMainWindow, QPushButton, QLabel, QVBoxLayout, QWidget, QFileDialog
from PyQt5.QtGui import QColor

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("World of Tanks Replay Player")
        self.setGeometry(100, 100, 400, 250)

        self.executable_path = ""
        self.feedback_label = QLabel("No executable selected.")
        self.feedback_label.setStyleSheet("color: red")

        self.select_executable_button = QPushButton("Select Executable")
        self.select_executable_button.clicked.connect(self.select_executable)

        self.play_replay_button = QPushButton("Play Replay")
        self.play_replay_button.clicked.connect(self.play_replay)
        self.play_replay_button.setStyleSheet("background-color: green")

        layout = QVBoxLayout()
        layout.addWidget(self.select_executable_button)
        layout.addWidget(self.play_replay_button)
        layout.addWidget(self.feedback_label)

        central_widget = QWidget()
        central_widget.setLayout(layout)
        self.setCentralWidget(central_widget)

    def select_executable(self):
        self.executable_path, _ = QFileDialog.getOpenFileName(self, "Select Executable", "", "Executable Files (*.exe)")
        if self.executable_path:
            self.feedback_label.setText("Selected executable: " + self.executable_path)
            self.feedback_label.setStyleSheet("color: green")
        else:
            self.feedback_label.setText("No executable selected.")
            self.feedback_label.setStyleSheet("color: red")

    def play_replay(self):
        if not self.executable_path:
            self.feedback_label.setText("Please select an executable.")
            self.feedback_label.setStyleSheet("color: red")
            return

        replay_file_path, _ = QFileDialog.getOpenFileName(self, "Select Replay File", "", "Replay Files (*.wotreplay)")
        if replay_file_path.endswith(".wotreplay"):
            self.feedback_label.setText("Playing replay: " + replay_file_path)
            self.feedback_label.setStyleSheet("color: green")
            # Add your code here to play the replay using the selected executable
        else:
            self.feedback_label.setText("Please select a valid replay file.")
            self.feedback_label.setStyleSheet("color: red")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
