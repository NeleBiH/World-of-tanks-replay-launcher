# Write your code here :-)
import tkinter as tk
from tkinter import filedialog
import subprocess

executable_path = ""
window = tk.Tk()
window.title("World of Tanks Replay Launcher")
window.geometry("500x300")

def select_executable():
    global executable_path
    executable_path = filedialog.askopenfilename(filetypes=[("Executable Files", ".exe")])
    if executable_path:
        feedback_text.config(text="Selected executable: " + executable_path, fg="green")
    else:
        feedback_text.config(text="No executable selected.", fg="red")

def play_replay():
    if not executable_path:
        feedback_text.config(text="Please select an executable.", fg="red")
        return
    replay_file_path = filedialog.askopenfilename(filetypes=[("Replay Files", ".wotreplay")])
    if replay_file_path.endswith(".wotreplay"):
        feedback_text.config(text="Playing replay: " + replay_file_path, fg="green")
        subprocess.run(["wine", executable_path, replay_file_path])
    else:
        feedback_text.config(text="Please select a valid replay file.", fg="red")

executable_button = tk.Button(window, text="Select Executable", command=select_executable)
executable_button.pack()

play_button = tk.Button(window, text="Play Replay", command=play_replay, bg="green")
play_button.pack()

feedback_text = tk.Label(window, text="No executable selected.", fg="red")
feedback_text.pack(pady=10)

window.mainloop()
