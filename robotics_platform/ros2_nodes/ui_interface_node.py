import rclpy
from rclpy.node import Node
from std_msgs.msg import String
from robotics_platform.ui.pygame_ui import PygameUI

class UIInterfaceNode(Node):
    def __init__(self, ui_instance=None):
        super().__init__('ui_interface_node')
        
        # Create UI if not provided (for standalone execution)
        self.ui = ui_instance if ui_instance else PygameUI()
        if not ui_instance:
            self.ui.start()
        
        # Subscribe to topics for updating UI
        self.emoji_subscription = self.create_subscription(
            String,
            'robot/emoji',
            self.emoji_callback,
            10)
            
        self.log_subscription = self.create_subscription(
            String,
            'robot/logs',
            self.log_callback,
            10)
        
        # Create publishers for UI events
        self.ui_event_publisher = self.create_publisher(
            String,
            'ui/events',
            10)
            
        self.get_logger().info('UI Interface Node initialized')
    
    def emoji_callback(self, msg):
        self.ui.update_emoji(msg.data)
    
    def log_callback(self, msg):
        self.ui.update_logs(msg.data)

def main(args=None):
    rclpy.init(args=args)
    node = UIInterfaceNode()
    
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.ui.stop()
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()
