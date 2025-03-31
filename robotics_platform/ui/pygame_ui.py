import pygame
import threading
import time

class PygameUI:
    def __init__(self):
        self.screen = None
        self.running = False
        self.emoji = "🤖"
        self.logs = []
        self.width, self.height = 1080, 1920
        self.lock = threading.Lock()

    def start(self):
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        pygame.init()
        self.screen = pygame.display.set_mode((self.width, self.height))
        pygame.display.set_caption("ROS2 Robotics Platform UI")
        self.running = True

        while self.running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False

            self.screen.fill((0, 0, 0))  # Black background

            with self.lock:
                # Render emoji on the top half
                font = pygame.font.Font(None, 200)
                emoji_surface = font.render(self.emoji, True, (255, 255, 255))
                self.screen.blit(emoji_surface, (self.width // 2 - emoji_surface.get_width() // 2, self.height // 4))

                # Render logs on the bottom half
                log_font = pygame.font.Font(None, 36)
                for i, log in enumerate(self.logs[-10:]):  # Show last 10 logs
                    log_surface = log_font.render(log, True, (255, 255, 255))
                    self.screen.blit(log_surface, (10, self.height // 2 + i * 40))

            pygame.display.flip()
            time.sleep(0.033)  # ~30fps

        pygame.quit()

    def update_emoji(self, emoji):
        with self.lock:
            self.emoji = emoji

    def update_logs(self, log):
        with self.lock:
            self.logs.append(log)

    def stop(self):
        self.running = False
