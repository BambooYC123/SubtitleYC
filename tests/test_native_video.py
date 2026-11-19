"""Frame-accuracy tests for the native preview decoder, against a generated video."""

import tempfile
import unittest
from fractions import Fraction
from pathlib import Path

import av
from PIL import Image

from subtitleyc.native_video import NativeVideoDecoder

FRAMES = 40
FPS = 20
GOP = 12
SIZE = (64, 48)


def _level(index: int) -> int:
    """Each frame is one flat grey level, so a decoded picture identifies its frame."""

    return 20 + index * 5


def _write_video(path: Path, start_offset_frames: int = 0) -> None:
    with av.open(str(path), "w") as container:
        stream = container.add_stream("mpeg4", rate=FPS)
        stream.width, stream.height = SIZE
        stream.pix_fmt = "yuv420p"
        stream.gop_size = GOP
        stream.bit_rate = 2_000_000
        for index in range(FRAMES):
            frame = av.VideoFrame.from_image(Image.new("RGB", SIZE, (_level(index),) * 3))
            frame.pts = index + start_offset_frames
            frame.time_base = Fraction(1, FPS)
            for packet in stream.encode(frame):
                container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)


def _shown_frame(image: Image.Image) -> int:
    grey = image.convert("L").resize((1, 1)).getpixel((0, 0))
    return round((grey - 20) / 5)


class NativeVideoDecoderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.folder = tempfile.TemporaryDirectory()
        cls.video = Path(cls.folder.name) / "frames.mp4"
        _write_video(cls.video)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.folder.cleanup()

    def _decoder(self, frame_count: int = FRAMES) -> NativeVideoDecoder:
        metadata = {"width": SIZE[0], "height": SIZE[1], "fps": FPS, "frame_count": frame_count,
                    "duration": frame_count / FPS}
        decoder = NativeVideoDecoder(str(self.video), metadata)
        self.addCleanup(decoder.close)
        return decoder

    def test_every_frame_is_exact_forwards_and_backwards(self) -> None:
        decoder = self._decoder()
        for index in [0, 1, 5, 13, 30, 39, 22, 11, 12, 3]:
            image, shown = decoder.get_frame(index, SIZE)
            self.assertEqual(shown, index)
            self.assertEqual(_shown_frame(image), index, f"asked for frame {index}")

    def test_last_frame_stays_put_when_asked_repeatedly(self) -> None:
        decoder = self._decoder()
        last = FRAMES - 1
        for _ in range(3):
            image, _shown = decoder.get_frame(last, SIZE)
            self.assertEqual(_shown_frame(image), last)

    def test_metadata_longer_than_the_video_shows_the_last_frame_not_a_keyframe(self) -> None:
        # ffprobe often reports ceil(duration * fps), a few frames more than can be decoded.
        decoder = self._decoder(frame_count=FRAMES + 6)
        past_the_end = FRAMES + 4
        for _ in range(3):
            image, shown = decoder.get_frame(past_the_end, SIZE)
            self.assertEqual(shown, past_the_end)
            self.assertEqual(_shown_frame(image), FRAMES - 1)
        # After hitting the end, an earlier frame must still decode exactly (not its keyframe).
        image, _shown = decoder.get_frame(FRAMES - 3, SIZE)
        self.assertEqual(_shown_frame(image), FRAMES - 3)

    def test_repeat_request_is_served_from_cache_without_seeking(self) -> None:
        decoder = self._decoder(frame_count=FRAMES + 6)
        decoder.get_frame(FRAMES + 4, SIZE)
        seeks: list[int] = []
        original_seek = decoder._seek
        decoder._seek = lambda index: (seeks.append(index), original_seek(index))[1]  # type: ignore[method-assign]
        decoder.get_frame(FRAMES + 4, SIZE)
        self.assertEqual(seeks, [])

    def test_video_that_does_not_start_at_zero_is_previewed_from_its_first_frame(self) -> None:
        shifted = Path(self.folder.name) / "shifted.ts"
        _write_video(shifted, start_offset_frames=50)
        metadata = {"width": SIZE[0], "height": SIZE[1], "fps": FPS, "frame_count": FRAMES, "duration": FRAMES / FPS}
        decoder = NativeVideoDecoder(str(shifted), metadata)
        self.addCleanup(decoder.close)
        if not decoder.stream.start_time:
            self.skipTest("container normalised the start time")
        for index in [0, 7, 25, 39, 14]:
            image, _shown = decoder.get_frame(index, SIZE)
            self.assertEqual(_shown_frame(image), index, f"asked for frame {index}")


if __name__ == "__main__":
    unittest.main()
