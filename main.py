#
# PyQt5-based video-sync example for VLC Python bindings
# Copyright (C) 2009-2010 the VideoLAN team
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston MA 02110-1301, USA.
#
"""
Based on the vlc videosync example from Saveliy Yusufov
Author: Stefan Murawski | @steveway
"""
import platform
import sys
import os
import json
import pathlib
import queue

import vlc
from PySide2 import QtWidgets, QtGui, QtCore
from PySide2.QtCore import QFile
from PySide2.QtUiTools import QUiLoader as uic

from networkmqtt import *


class Player(QtWidgets.QMainWindow):
    """A "master" Media Player using VLC and Qt
    """

    def __init__(self, master=None):
        QtWidgets.QMainWindow.__init__(self, master)
        # Create a basic vlc instance
        self.instance = vlc.Instance()

        self.mqtt_connection = None
        self.current_ip = ""
        self.current_port = 1883
        self.current_id = ""
        self.current_topic = ""
        self.offset = 0
        self.is_connected = False

        self.media = None
        self.is_maximized = False
        self.is_visible = True
        self.last_update_time = 0
        # Create an empty vlc media player
        self.mediaplayer = self.instance.media_player_new()

        self.create_ui()
        try:
            self.load_settings()
        except (FileNotFoundError, json.decoder.JSONDecodeError):
            pass
        self.data_queue = queue.Queue()
        self.is_paused = False
        self.gui_timer = QtCore.QTimer(self)
        self.timer = QtCore.QTimer(self)
        # self.change_server_state()
        self.timer.setInterval(10)
        self.timer.timeout.connect(self.update_ui_client)
        self.timer.start()

    def create_ui(self):
        """Set up the user interface, signals & slots
        """
        self.main_window = self.load_ui_widget(os.path.join(os.getcwd(), "videosync.ui"))
        self.main_window.centralwidget.setLayout(self.main_window.vboxlayout)

        # In this widget, the video will be drawn
        if platform.system() == "Darwin":  # for MacOS
            self.main_window.videoframe = QtWidgets.QMacCocoaViewContainer(0)

        self.palette = self.main_window.videoframe.palette()
        self.palette.setColor(QtGui.QPalette.Window, QtGui.QColor(0, 0, 0))
        self.main_window.videoframe.setPalette(self.palette)

        # Create the position slider (QSlider)
        self.main_window.positionslider.sliderMoved.connect(self.set_position)
        # self.positionslider.sliderPressed.connect(self.set_position)
        self.main_window.positionslider.sliderMoved.connect(self.update_time_label)

        self.main_window.volume_slider.sliderMoved.connect(self.update_volume)

        # Create the "previous frame" button
        self.main_window.previousframe.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_MediaSkipBackward))
        self.main_window.previousframe.clicked.connect(self.on_neg_offset)

        # Create the play button and connect it to the play/pause function
        self.main_window.playbutton.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_MediaPlay))
        self.main_window.playbutton.clicked.connect(self.play_pause)

        # Create the "next frame" button
        self.main_window.nextframe.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_MediaSkipForward))
        self.main_window.nextframe.clicked.connect(self.on_pos_offset)

        # Create the "decrease playback rate" button
        self.main_window.decr_pb_rate.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_MediaSeekBackward))
        self.main_window.decr_pb_rate.clicked.connect(self.decr_mov_play_rate)

        # Create the stop button and connect it to the stop function
        self.main_window.stopbutton.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_MediaStop))
        self.main_window.stopbutton.clicked.connect(self.stop)

        self.main_window.maximize.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_TitleBarMaxButton))
        self.main_window.maximize.clicked.connect(self.on_maximize)

        # Create the "increase playback rate" button
        self.main_window.incr_pb_rate.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_MediaSeekForward))
        self.main_window.incr_pb_rate.clicked.connect(self.incr_mov_play_rate)

        self.main_window.videoframe.keyPressEvent = self.on_move

        # File menu
        file_menu = self.main_window.menu_bar.addMenu("File")
        self.audio_lang_menu = self.main_window.menu_bar.addMenu("Audio")
        self.sub_lang_menu = self.main_window.menu_bar.addMenu("Subtitles")

        # Create actions to load a new media file and to close the app
        open_action = QtWidgets.QAction("Load Video", self)
        close_action = QtWidgets.QAction("Close App", self)
        file_menu.addAction(open_action)
        file_menu.addAction(close_action)
        # test_combo = QtWidgets.QComboBox()
        # self.main_window.menu_bar.addWidget(test_combo)
        open_action.triggered.connect(self.open_file)
        close_action.triggered.connect(sys.exit)
        self.main_window.videoframe.setFocus()
        self.main_window.installEventFilter(self)
        self.main_window.ip_address.textChanged.connect(self.update_mqtt)
        self.main_window.client_id_input.textChanged.connect(self.update_mqtt)
        self.main_window.topic_input.textChanged.connect(self.update_mqtt)
        self.main_window.server_input.stateChanged.connect(self.change_server_state)
        self.main_window.connect_button.clicked.connect(self.connect_to_mqtt)
        self.main_window.top_control_box.setEnabled(False)
        self.main_window.playbutton.setEnabled(False)
        self.main_window.decr_pb_rate.setEnabled(False)
        self.main_window.incr_pb_rate.setEnabled(False)
        self.main_window.stopbutton.setEnabled(False)

    def update_volume(self, event=None):
        self.mediaplayer.audio_set_volume(self.main_window.volume_slider.value())

    def on_pos_offset(self):
        self.offset += 200
        self.main_window.offset_label.setText("Offset: {}ms".format(self.offset))

    def on_neg_offset(self):
        self.offset -= 200
        self.main_window.offset_label.setText("Offset: {}ms".format(self.offset))

    def change_server_state(self, event=None):
        if self.main_window.server_input.isChecked():
            self.main_window.previousframe.clicked.disconnect()
            self.main_window.nextframe.clicked.disconnect()
            self.main_window.previousframe.clicked.connect(self.on_previous_frame)
            self.main_window.nextframe.clicked.connect(self.on_next_frame)
            self.main_window.top_control_box.setEnabled(True)
            # self.main_window.bottom_control_box.setEnabled(True)
            self.main_window.playbutton.setEnabled(True)
            self.main_window.decr_pb_rate.setEnabled(True)
            self.main_window.incr_pb_rate.setEnabled(True)
            self.main_window.stopbutton.setEnabled(True)
            self.timer.timeout.disconnect()
            self.timer.setInterval(200)
            self.timer.timeout.connect(self.update_ui)
            self.timer.timeout.connect(self.update_time_label)
            self.timer.start()
        else:
            self.main_window.previousframe.clicked.disconnect()
            self.main_window.nextframe.clicked.disconnect()
            self.main_window.previousframe.clicked.connect(self.on_neg_offset)
            self.main_window.nextframe.clicked.connect(self.on_pos_offset)
            self.main_window.top_control_box.setEnabled(False)
            self.main_window.playbutton.setEnabled(False)
            self.main_window.decr_pb_rate.setEnabled(False)
            self.main_window.incr_pb_rate.setEnabled(False)
            self.main_window.stopbutton.setEnabled(False)
            self.timer.timeout.disconnect()
            self.timer.setInterval(10)
            self.timer.timeout.connect(self.update_ui_client)
            self.timer.start()

    def connect_to_mqtt(self, event=None):
        if not self.is_connected:
            if self.main_window.server_input.isChecked():
                self.mqtt_connection = Server(self.current_id, self.current_ip, self.current_port, self.current_topic,
                                              self.data_queue)
            else:
                self.mqtt_connection = Client(self.current_id, self.current_ip, self.current_port, self.current_topic,
                                              self.data_queue)
            self.is_connected = True
            self.main_window.connect_button.setText("Disconnect")
            self.main_window.ip_address.setEnabled(False)
            self.main_window.client_id_input.setEnabled(False)
            self.main_window.topic_input.setEnabled(False)
            self.main_window.server_input.setEnabled(False)
        else:
            self.mqtt_connection.disconnect()
            self.mqtt_connection = None
            self.is_connected = False
            self.main_window.connect_button.setText("Connect")
            self.main_window.ip_address.setEnabled(True)
            self.main_window.client_id_input.setEnabled(True)
            self.main_window.topic_input.setEnabled(True)
            self.main_window.server_input.setEnabled(True)

    def update_mqtt(self, event=None):
        self.current_ip = self.main_window.ip_address.text()
        self.current_id = self.main_window.client_id_input.text()
        self.current_topic = self.main_window.topic_input.text()
        self.save_settings()

    def load_settings(self):
        load_file = open("settings.json", "r")
        json_data = json.load(load_file)
        self.main_window.ip_address.setText(json_data["ip"])
        self.main_window.client_id_input.setText(json_data["id"])
        self.main_window.topic_input.setText(json_data["topic"])
        self.main_window.setGeometry(*json_data["window_coords"])
        load_file.close()

    def save_settings(self):
        save_file = open("settings.json", "w")
        json_data = {"ip": str(self.current_ip), "id": str(self.current_id), "topic": str(self.current_topic),
                     "window_coords": [self.main_window.geometry().x(), self.main_window.geometry().y(),
                                       self.main_window.geometry().width(), self.main_window.geometry().height()]}

        json.dump(json_data, save_file)
        save_file.close()

    def load_ui_widget(self, ui_filename, parent=None):
        loader = uic()
        file = QFile(ui_filename)
        file.open(QFile.ReadOnly)
        self.ui = loader.load(file, parent)
        file.close()
        return self.ui

    def eventFilter(self, object_, event):
        if object_ == self.main_window.topic_input:
            return False
        if event.type() == QtCore.QEvent.KeyPress:
            self.main_window.videoframe.setFocus()
            self.on_move()
        return False

    def on_maximize(self, event=None):
        if not self.is_maximized:
            self.main_window.bottom_control_box.hide()
            self.main_window.top_control_box.hide()
            self.main_window.mqtt_control_box.hide()
            self.main_window.menu_bar.hide()
            self.main_window.setWindowFlags(QtCore.Qt.WindowStaysOnTopHint | QtCore.Qt.FramelessWindowHint)
            self.main_window.showFullScreen()
            self.is_maximized = True
            self.is_visible = False
            self.main_window.videoframe.setFocus()
            self.main_window.vboxlayout.setContentsMargins(0, 0, 0, 0)
        else:
            self.main_window.top_control_box.show()
            self.main_window.bottom_control_box.show()
            self.main_window.mqtt_control_box.show()
            self.main_window.menu_bar.show()
            self.main_window.setWindowFlags(QtCore.Qt.Window)
            self.main_window.showNormal()
            self.main_window.resize(640, 480)
            self.is_maximized = False
            self.is_visible = True
            self.main_window.vboxlayout.setContentsMargins(11, 11, 11, 11)

    def on_move(self, event=None):
        if self.is_maximized:
            if not self.is_visible:
                self.gui_timer.setInterval(2000)
                self.gui_timer.timeout.connect(self.on_move)
                self.gui_timer.start()
                self.main_window.mqtt_control_box.show()
                self.main_window.top_control_box.show()
                self.main_window.bottom_control_box.show()
                self.main_window.menu_bar.show()
                self.is_visible = True
            else:
                self.gui_timer.stop()
                self.main_window.mqtt_control_box.hide()
                self.main_window.top_control_box.hide()
                self.main_window.bottom_control_box.hide()
                self.main_window.menu_bar.hide()
                self.is_visible = False

    def play_pause(self):
        """Toggle play/pause status
        """
        if self.mediaplayer.is_playing():
            signal = 'p'
            self.mediaplayer.pause()
            self.main_window.playbutton.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_MediaPlay))
            self.is_paused = True
            self.timer.stop()
        else:
            if self.mediaplayer.play() == -1:
                self.open_file()
                return

            signal = 'P'
            self.mediaplayer.play()
            self.main_window.playbutton.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_MediaPause))
            self.timer.start()
            self.is_paused = False

        # Reset the queue & send the appropriate signal, i.e., play/pause
        if self.main_window.server_input.isChecked():
            if self.is_connected:
                self.data_queue.queue.clear()
                self.data_queue.put('d')
                self.data_queue.put(signal)
                if not self.is_paused:
                    current_time = self.mediaplayer.get_time()
                    self.data_queue.put(current_time)

    def stop(self):
        """Stop player
        """
        self.mediaplayer.stop()
        self.main_window.playbutton.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_MediaPlay))

        # Reset the time label back to 00:00:00
        reset_time = QtCore.QTime(0, 0, 0, 0)
        self.main_window.timelabel.setText(reset_time.toString())

        # Reset the queue
        if self.main_window.server_input.isChecked():
            if self.is_connected:
                self.data_queue.queue.clear()
                self.data_queue.put('d')
                self.data_queue.put('S')

        # Reset the media position slider
        self.main_window.positionslider.setValue(0)

        self.timer.stop()

    def on_next_frame(self):
        """Go forward one frame.

            The Python VLC binding next_frame function causes a:

            "direct3d11 vout display error: SetThumbNailClip failed"

            error when next_frame is called while the video is playing,
            so we are using our own fucntion to get the next frame.
        """
        # self.mediaplayer.next_frame()
        next_frame_time = self.mediaplayer.get_time() + self.mspf()

        # Reset the queue & put the next frame's time into the queue
        if self.main_window.server_input.isChecked():
            if self.is_connected:
                self.data_queue.queue.clear()
                self.data_queue.put('d')
                self.data_queue.put(next_frame_time)
        self.update_time_label()
        self.mediaplayer.set_time(next_frame_time)

    def on_previous_frame(self):
        """Go backward one frame"""
        next_frame_time = self.mediaplayer.get_time() - self.mspf()

        # Reset the queue & put the next frame's time into the queue
        if self.main_window.server_input.isChecked():
            if self.is_connected:
                self.data_queue.queue.clear()
                self.data_queue.put('d')
                self.data_queue.put(next_frame_time)
        self.update_time_label()
        self.mediaplayer.set_time(next_frame_time)

    def mspf(self):
        """Milliseconds per frame"""
        return int(1000 // (self.mediaplayer.get_fps() or 25))

    def incr_mov_play_rate(self):
        """Increase the movie play rate by a factor of 2."""
        if self.mediaplayer.get_rate() >= 64:
            return

        rate = self.mediaplayer.get_rate() * 2
        result = self.mediaplayer.set_rate(rate)
        if result == 0:
            if self.main_window.server_input.isChecked():
                if self.is_connected:
                    self.data_queue.queue.clear()
                    self.data_queue.put('d')
                    self.data_queue.put('>')
            self.update_pb_rate_label()

    def decr_mov_play_rate(self):
        """Decrease the movie play rate by a factor of 2."""
        if self.mediaplayer.get_rate() <= 0.125:
            return

        rate = self.mediaplayer.get_rate() * 0.5
        result = self.mediaplayer.set_rate(rate)
        if result == 0:
            if self.main_window.server_input.isChecked():
                if self.is_connected:
                    self.data_queue.queue.clear()
                    self.data_queue.put('d')
                    self.data_queue.put('<')
            self.update_pb_rate_label()

    def open_file(self):
        """Open a media file in a MediaPlayer
        """
        dialog_txt = "Choose Media File"
        filename = QtWidgets.QFileDialog.getOpenFileName(self, dialog_txt, os.path.expanduser('~'))
        if not filename[0]:
            return

        # getOpenFileName returns a tuple, so use only the actual file name
        self.media = self.instance.media_new(filename[0])

        # Put the media in the media player
        self.mediaplayer.set_media(self.media)

        # Parse the metadata of the file
        self.media.parse()

        # Set the title of the track as window title
        self.main_window.setWindowTitle("MQTT Sync Player: {}".format(self.media.get_meta(0)))

        # The media player has to be 'connected' to the QFrame (otherwise the
        # video would be displayed in it's own window). This is platform
        # specific, so we must give the ID of the QFrame (or similar object) to
        # vlc. Different platforms have different functions for this.
        if platform.system() == "Linux":  # for Linux using the X Server
            self.mediaplayer.set_xwindow(int(self.main_window.videoframe.winId()))
        elif platform.system() == "Windows":  # for Windows
            self.mediaplayer.set_hwnd(int(self.main_window.videoframe.winId()))
        elif platform.system() == "Darwin":  # for MacOS
            self.mediaplayer.set_nsobject(int(self.main_window.videoframe.winId()))

        list_of_track_actions = []
        self.audio_lang_menu.clear()
        tracks = self.media.tracks_get()
        for track in tracks:
            if track.type == vlc.TrackType.audio:
                print(track)
                track_desc = "None"
                try:
                    track_desc = track.description.decode()
                except AttributeError:
                    pass
                track_lang = "None"
                try:
                    track_lang = track.language.decode()
                except AttributeError:
                    pass
                list_of_track_actions.append(
                    QtWidgets.QAction("{}_{}_{}".format(track.id, track_desc, track_lang), self))
                self.audio_lang_menu.addAction(list_of_track_actions[-1])
                list_of_track_actions[-1].triggered.connect(self.on_track_change)
                # list_of_track_actions[-1].installEventFilter(self)
        list_of_subs = []
        self.sub_lang_menu.clear()
        tracks = self.media.tracks_get()
        list_of_subs.append(QtWidgets.QAction("-1_None", self))
        self.sub_lang_menu.addAction(list_of_subs[-1])
        list_of_subs[-1].triggered.connect(self.on_sub_change)
        for subtitle in tracks:
            print(subtitle)
            if subtitle.type == vlc.TrackType.ext:
                subtitle_lang = "None"
                try:
                    subtitle_lang = subtitle.language.decode()
                except AttributeError:
                    pass
                list_of_subs.append(QtWidgets.QAction("{}_{}".format(subtitle.id, subtitle_lang), self))
                self.sub_lang_menu.addAction(list_of_subs[-1])
                list_of_subs[-1].triggered.connect(self.on_sub_change)

        list_of_subs.append(QtWidgets.QAction("-2_External File", self))
        self.sub_lang_menu.addAction(list_of_subs[-1])
        list_of_subs[-1].triggered.connect(self.on_sub_change)
        # print(vlc.libvlc_video_get_spu_count(self.media))

        if os.path.exists(filename[0].rsplit(".", 1)[0] + ".srt"):
            if os.path.isfile(filename[0].rsplit(".", 1)[0] + ".srt"):
                self.mediaplayer.video_set_subtitle_file(filename[0].rsplit(".", 1)[0] + ".srt")
        self.main_window.volume_slider.setValue(50)

    def on_track_change(self, event=None):
        action = self.sender()
        self.mediaplayer.audio_set_track(int(action.text().split("_")[0]))

    def on_sub_change(self, event=None):
        action = self.sender()
        if int(action.text().split("_")[0]) != -2:
            self.mediaplayer.video_set_spu(int(action.text().split("_")[0]))
        else:
            dialog_txt = "Choose Subtitle File"
            filename = QtWidgets.QFileDialog.getOpenFileName(self, dialog_txt, os.path.expanduser('~'))
            if not filename[0]:
                return
            uri_path = pathlib.Path(filename[0]).as_uri()
            self.media.slaves_add(vlc.MediaSlaveType.subtitle, 4, uri_path)
            self.media.parse()
            # self.mediaplayer.video_set_subtitle_file(filename[0])
            self.sub_lang_menu.clear()
            list_of_subs = []
            tracks = self.media.tracks_get()
            list_of_subs.append(QtWidgets.QAction("-1_None", self))
            self.sub_lang_menu.addAction(list_of_subs[-1])
            list_of_subs[-1].triggered.connect(self.on_sub_change)
            for subtitle in tracks:
                print(subtitle)
                if subtitle.type == vlc.TrackType.ext:
                    subtitle_lang = "None"
                    try:
                        subtitle_lang = subtitle.language.decode()
                    except AttributeError:
                        pass
                    list_of_subs.append(QtWidgets.QAction("{}_{}".format(subtitle.id, subtitle_lang), self))
                    self.sub_lang_menu.addAction(list_of_subs[-1])
                    list_of_subs[-1].triggered.connect(self.on_sub_change)

            list_of_subs.append(QtWidgets.QAction("-2_External File", self))
            self.sub_lang_menu.addAction(list_of_subs[-1])
            list_of_subs[-1].triggered.connect(self.on_sub_change)

    def set_position(self):
        """Set the movie position according to the position slider.

        The vlc MediaPlayer needs a float value between 0 and 1, Qt uses
        integer variables, so you need a factor; the higher the factor,
        the more precise are the results (1000 should suffice).
        """
        # Set the media position to where the slider was dragged
        self.timer.stop()
        pos = self.main_window.positionslider.value()

        if pos >= 0:
            if self.main_window.server_input.isChecked():
                if self.is_connected:
                    self.data_queue.queue.clear()
                    self.data_queue.put('d')
            current_time = self.mediaplayer.get_time()

            # If the player is stopped, do not attempt to send a -1!!!
            if current_time == -1:
                self.timer.start()
                return
            if self.main_window.server_input.isChecked():
                if self.is_connected:
                    self.data_queue.put(current_time)
            self.last_update_time = current_time

        self.mediaplayer.set_position(pos * .001)
        self.timer.start()

    def update_ui(self):
        """Updates the user interface"""

        # Set the slider's position to its corresponding media position
        # Note that the setValue function only takes values of type int,
        # so we must first convert the corresponding media position.
        media_pos = int(self.mediaplayer.get_position() * 1000)
        self.main_window.positionslider.setValue(media_pos)

        if media_pos >= 0 and self.mediaplayer.is_playing():
            current_time = self.mediaplayer.get_time()
            if current_time > self.last_update_time + 5000:
                if self.main_window.server_input.isChecked():
                    if self.is_connected:
                        self.data_queue.put(current_time)
                self.last_update_time = current_time
        else:
            if self.main_window.server_input.isChecked():
                if self.is_connected:
                    self.data_queue.queue.clear()

        # No need to call this function if nothing is played
        if not self.mediaplayer.is_playing():
            self.timer.stop()

            # After the video finished, the play button stills shows "Pause",
            # which is not the desired behavior of a media player.
            # This fixes that "bug".
            if not self.is_paused:
                self.stop()

    def update_ui_client(self):
        if not self.data_queue.empty():
            val = self.data_queue.get_nowait()
        else:
            return
        print(val)
        if val == '<':
            self.mediaplayer.set_rate(self.mediaplayer.get_rate() * 0.5)
            return
        if val == '>':
            self.mediaplayer.set_rate(self.mediaplayer.get_rate() * 2)
            return
        if val == 'P':
            self.mediaplayer.play()
            return
        if val == 'p':
            self.mediaplayer.pause()
            return
        if val == 'S':
            self.mediaplayer.stop()
            return

        val = int(val) + self.offset
        if val != self.mediaplayer.get_time():
            self.mediaplayer.set_time(val)

    def update_time_label(self):
        mtime = QtCore.QTime(0, 0, 0, 0)
        self.time = mtime.addMSecs(self.mediaplayer.get_time())
        self.main_window.timelabel.setText(self.time.toString())

    def update_pb_rate_label(self):
        self.main_window.pb_rate_label.setText("Playback rate: {}x".format(str(self.mediaplayer.get_rate())))


def main():
    """Entry point for our simple vlc player
    """
    app = QtWidgets.QApplication(sys.argv)
    player = Player()
    player.main_window.show()
    player.resize(640, 480)
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
