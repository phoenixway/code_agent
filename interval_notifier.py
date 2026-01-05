#!/usr/bin/env python3
"""
Interval Notifier for Android Termux
This script asks for an interval in minutes and shows a system notification
at that interval repeatedly.
"""

import subprocess
import time
import sys

def show_notification(title="Interval Notifier", message="Time's up!"):
    """Show a system notification using termux-notification."""
    try:
        subprocess.run([
            'termux-notification',
            '--title', title,
            '--content', message,
            '--sound'  # Optional: add sound
        ], check=True)
    except subprocess.CalledProcessError as e:
        print(f"Failed to show notification: {e}", file=sys.stderr)
    except FileNotFoundError:
        print("Error: 'termux-notification' command not found. Ensure Termux:API is installed.", file=sys.stderr)
        print("Install via: pkg install termux-api", file=sys.stderr)
        sys.exit(1)

def main():
    print("=== Interval Notifier for Termux ===")
    print("This script will show a notification at your specified interval.")
    print("Press Ctrl+C to stop.\n")
    
    # Get interval input
    while True:
        try:
            interval_input = input("Enter interval in minutes (e.g., 0.5 for 30 seconds): ")
            interval_min = float(interval_input)
            if interval_min <= 0:
                print("Interval must be positive. Try again.")
                continue
            break
        except ValueError:
            print("Invalid number. Please enter a numeric value.")
    
    interval_sec = interval_min * 60
    print(f"Notification will show every {interval_min} minutes ({interval_sec:.1f} seconds).")
    print("Starting... (first notification now)")
    
    # Initial notification
    show_notification(title="Interval Notifier Started", 
                      message=f"Notifications every {interval_min} min.")
    
    # Loop
    count = 1
    try:
        while True:
            time.sleep(interval_sec)
            show_notification(title=f"Notification #{count}", 
                              message=f"Interval: {interval_min} minutes elapsed.")
            count += 1
    except KeyboardInterrupt:
        print("\nStopped by user.")
        show_notification(title="Interval Notifier Stopped", 
                          message="Notifications terminated.")

if __name__ == "__main__":
    main()
