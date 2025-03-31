#!/usr/bin/env python3

import rclpy
from robotics_platform.core.robotics_loop import RoboticsLoop

def main():
    """Main entry point for the robotics platform."""
    # Initialize ROS2
    rclpy.init()
    try:
        robotics_loop = RoboticsLoop()
        robotics_loop.run()
    except KeyboardInterrupt:
        print("Shutting down...")
    finally:
        rclpy.shutdown()

if __name__ == "__main__":
    main()
