# Standard library imports.
import socket
import select
import random
import os
import sys
import logging
logger = logging.getLogger(__name__)
handler = logging.StreamHandler(sys.stdout)
#logger.setLevel(logging.DEBUG)
#formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
formatter = logging.Formatter("%(name)s - %(levelname)s - %(message)s")
handler.setFormatter(formatter)
logger.addHandler(handler)

from enum import Enum
import configparser

# Related third party imports.
import pygame as pg
try:
    import gif_pygame as gif_pg
    animated_images_supported: bool = True
except ModuleNotFoundError:
    logger.error("gif_pygame was not found! Without the gif_pygame library animated graphics are not supported. Please install the gif_pygame fork from https://github.com/grrchen/gif-pygame if you want to use animated graphics like gifs, or apngs.")
    animated_images_supported: bool = False

# Local application/library specific imports.


DEFAULT_CAPTION: str = "PNGPet"
DEFAULT_HOST: str = "localhost"
DEFAULT_PORT: int = 8090
SCREEN_WIDTH: int = 800
SCREEN_HEIGHT: int = 600

framerate: int = 60


class StateGroup(pg.sprite.Group):

    def resize(self, w, h):
        for sprite in self.sprites():
            sprite.resize(w, h)

    def end_loop(self):
        self.sprites()[0].end_loop()

    @property
    def ended(self):
        return self.sprites()[0].ended

    @ended.setter
    def ended(self, value):
        self.sprites()[0].ended = value
        self.sprites()[0].reset()


ANIMATED_FILE_EXT = (".apng", ".gif")


def scale(img, dimension):
    if isinstance(img, gif_pg.GIFPygame):
        scaled_image = img.copy()
        gif_pg.transform.scale(scaled_image, dimension)
    else:
        scaled_image = pg.transform.scale(img, dimension)
    #print("scaled_image:", scaled_image, dir(scaled_image))
    return scaled_image


class EndedException(Exception):
    pass


class PNGPetState(pg.sprite.Sprite):

    ended: bool = False
    _image = None

    def end_loop(self):
        self._image.loops[0] = self._image.loops[1]

    def load_image(self, image_path, loops=0):
        if animated_images_supported:
            for file_ext in ANIMATED_FILE_EXT:
                if image_path.lower().endswith(file_ext):
                    image = gif_pg.load(image_path, loops)
                    break
            else:
                image = pg.image.load(image_path)
        else:
            image = pg.image.load(image_path)
        return image

    def scale_image(self, image, screen_width=SCREEN_WIDTH, screen_height=SCREEN_HEIGHT):
        w, h = image.get_size()
        ratio = self.get_ratio(w, h, screen_width, screen_height)
        width = int(w*ratio)
        height = int(h*ratio)
        scaled_image = scale(image, (width, height))
        if image is self._orig_image:
            self._image = scaled_image
        return scaled_image

    def __init__(self, pos, idle_image_path, change_image_path):
        super().__init__()
        self._last_resize_req = (SCREEN_WIDTH, SCREEN_HEIGHT)
        self._orig_idle_image = orig_idle_image = self.load_image(idle_image_path, 40)
        self._orig_change_image = orig_change_image = self.load_image(change_image_path)
        self._orig_image = self._orig_idle_image
        self._scaled_idle_image = self.scale_image(orig_idle_image)
        self._scaled_change_image = self.scale_image(orig_change_image)
        self._image = self._scaled_idle_image
        self.rect = self._image.get_rect()
        #self.rect.center = pos
        self.time = pg.time.get_ticks()

    def get_ratio(self, w, h, sw, sh):
        rw = sw / w
        rh = sh / h
        ratio = rw if rw < rh else rh
        return ratio

    def resize(self, w, h):
        resize_req = (w, h)
        if self._last_resize_req == resize_req:
            logger.debug("Ignoring request, size did not change")
            return
        self._last_resize_req = resize_req
        self._scaled_idle_image = self.scale_image(self._orig_idle_image, w, h)
        self._scaled_change_image = self.scale_image(self._orig_change_image, w, h)

    def reset(self):
        self._scaled_idle_image.reset()
        self._scaled_change_image.reset()

    def update(self):
        if self.ended:
            raise EndedException("Update was called although the sprite is finished, the sprite must be reset first.")
        if self._image is self._scaled_idle_image:
            if self._image.ended:
                self._image = self._scaled_change_image
                self._orig_image = self._orig_change_image
        elif self._image is self._scaled_change_image:
            if self._image.ended:
                self._image = self._scaled_idle_image
                self._orig_image = self._orig_idle_image
                self.ended = True

    @property
    def image(self):
        #print("image", self._image)
        if isinstance(self._image, gif_pg.GIFPygame):
            return self._image.blit_ready()
        return self._image


class App:
    _host: str
    _port: int
    _s_width: int
    _s_height: int
    _state_index: int = 0

    def __init__(self):
        self.loop()

    def connect(self):
        self._server = server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.setblocking(False)
        server.bind((self._host, self._port))
        server.listen(5) # become a server socket, maximum 5 connections

    def load_config(self):
        self._config = config = configparser.ConfigParser()
        config.read('config.ini')

    def load_app_config(self):
        try:
            app_config = self._config["app"]
        except KeyError:
            app_config = self._config["app"] = {"background_color": "magenta", 
                "caption": DEFAULT_CAPTION, 
                "host": DEFAULT_HOST, "port": DEFAULT_PORT}
        self._background_color: str = app_config.get("background_color", "magenta")
        self._host: str = app_config.get("host", DEFAULT_HOST) 
        self._port: int = int(app_config.get("port", DEFAULT_PORT)) 
        self._app_config = app_config

    def load_states(self):
        config = self._config
        self._states = states = []
        #c_sections = config.sections()
        state1 = config["state1"]
        state2 = config["state2"]
        for state in (state1, state2):
            base_dir = state.get("base_dir", "")
            idle_image = state.get("idle_image", None)
            change_image = state.get("change_image", None)
            idle_image_path = os.path.join(base_dir, idle_image)
            change_image_path = os.path.join(base_dir, change_image)
            png_pet_state = PNGPetState((0, 0), idle_image_path, change_image_path)
            png_pet_state.resize(self._s_width, self._s_height)
            state_group = StateGroup()
            state_group.add(png_pet_state)
            states.append(state_group)

    def loop(self):
        self.load_config()
        self.load_app_config()

        self.connect()
        server = self._server
        socket_list = [server]

        # Initialise pygame
        pg.init()
        pg.display.set_caption(self._app_config.get("caption", DEFAULT_CAPTION))

        screen = pg.display.set_mode([SCREEN_WIDTH, SCREEN_HEIGHT], pg.RESIZABLE)
        background_color = self._background_color
        logger.debug(f"background_color: {background_color}")
        screen.fill(background_color)
        s_width, s_height = screen.get_width(), screen.get_height()
        self._s_width, self._s_height = s_width, s_height

        # Create sprites
        self.load_states()
        states: list = self._states
        png_pet_state = states[0]
        new_state_index = None
        i: int = 0

        clock = pg.time.Clock()

        # Main loop, run until window closed
        running = True
        while running:
            # Get the list sockets which are readable
            try:
                inputready, outputready, exceptready = select.select(socket_list, [], [], 0.01)
            except select.error:
                break
            except socket.error:
                break

            for s in inputready:
                if s == server:
                    # handle the server socket
                    client, address = server.accept()
                    logger.info(f"got connection {client.fileno()} from {address}")
                    socket_list.append(client)
                elif s == sys.stdin:
                    # handle standard input
                    junk = sys.stdin.readline()
                    running = 0
                else:
                    # handle all other sockets
                    try:
                        # data = s.recv(BUFSIZ)
                        data = s.recv(1024)
                        if data:
                            cmd, body = data.split(b":", 1)
                            body = body.strip()
                            if cmd == b"state":
                                new_state_index = int(body)
                                if new_state_index < len(states) and new_state_index != i:
                                    png_pet_state.end_loop()
                                else:
                                    logger.error("State index out of range")
                                    new_state_index = None
                            else:
                                logger.error("Unknown cmd")
                        else:
                            logger.info(f"{s.fileno()} closed connection")
                            s.close()
                            socket_list.remove(s)
                    except (socket.error):
                        # Remove
                        socket_list.remove(s)

            png_pet_state.update()
            if png_pet_state.ended:
                if new_state_index is None or new_state_index == i:
                    i += 1
                    if i == len(states):
                        i = 0
                else:
                    i = new_state_index
                    new_state_index = None
                logger.debug(f"states: {i}")
                png_pet_state = states[i]
                s_width, s_height = self._s_width, self._s_height
                png_pet_state.resize(s_width, s_height)
                png_pet_state.ended = False

            # Check events
            for event in pg.event.get():
                #print("even type:", event.type)
                if event.type == pg.QUIT:
                    running = False
                elif event.type == pg.VIDEORESIZE:
                    self._s_width, self._s_height = screen.get_width(), screen.get_height()
                    s_width, s_height = self._s_width, self._s_height
                    png_pet_state.resize(s_width, s_height)
                    pg.display.update()
                    #screen = pg.display.set_mode([s_width, s_height], pg.RESIZABLE)
                elif event.type == pg.VIDEOEXPOSE:
                    pg.display.update()
            screen.fill(background_color)
            png_pet_state.draw(screen)
            pg.display.flip()
            clock.tick(framerate)

        # close pygame
        pg.quit()


def main():
    app = App()


if __name__ == "__main__":
    main()
