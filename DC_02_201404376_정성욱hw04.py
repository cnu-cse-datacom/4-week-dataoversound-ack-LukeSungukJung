from __future__ import print_function

import sys
import wave

from io import StringIO

import alsaaudio
import colorama
import numpy as np
import time

from reedsolo import RSCodec, ReedSolomonError
from termcolor import cprint
from pyfiglet import figlet_format

HANDSHAKE_START_HZ = 4096
HANDSHAKE_END_HZ = 5120 + 1024
MY_ID_NUMBER = "201404376"
MY_ID_LIST = [3, 2, 3, 0, 3, 1, 3, 4, 3, 0, 3, 4, 3, 3, 3, 7, 3, 6]
MY_ID_LEN = len(MY_ID_LIST)
MY_INCLUDE = False
START_HZ = 1024
STEP_HZ = 256
BITS = 4

FEC_BYTES = 4

import numpy
import pyaudio

ll_make_sound = []

def convert_hz(asc_list):
    asc_list = [aa*STEP_HZ+START_HZ for aa in asc_list]
    return asc_list


def make_sound(asc_list):
    hz_list= convert_hz(asc_list)
    hz_list.insert(0,HANDSHAKE_START_HZ)
    hz_list.append(HANDSHAKE_END_HZ)
    convert_sound(hz_list)

def convert_sound(data_list):
    p = pyaudio.PyAudio()
    stream = p.open(format=pyaudio.paFloat32, channels=1, rate=44100, output=True)
    for hz in data_list:
        print(hz)
        samples = np.sin((np.pi*hz*2*np.arange(44100))/44100).astype(np.float32)
        samples = np.array(samples);
        stream.write(samples)
    stream.close()
def test_pyaudio():
    p = pyaudio.PyAudio()
    stream =p.open(format=pyaudio.paFloat32,channels=1,rate=44100,output=True)






def stereo_to_mono(input_file, output_file):
    inp = wave.open(input_file, 'r')
    params = list(inp.getparams())
    params[0] = 1 # nchannels
    params[3] = 0 # nframes

    out = wave.open(output_file, 'w')
    out.setparams(tuple(params))

    frame_rate = inp.getframerate()
    frames = inp.readframes(inp.getnframes())
    data = np.fromstring(frames, dtype=np.int16)
    left = data[0::2]
    out.writeframes(left.tostring())

    inp.close()
    out.close()

def yield_chunks(input_file, interval):
    wav = wave.open(input_file)
    frame_rate = wav.getframerate()

    chunk_size = int(round(frame_rate * interval))
    total_size = wav.getnframes()

    while True:
        chunk = wav.readframes(chunk_size)
        if len(chunk) == 0:
            return

        yield frame_rate, np.fromstring(chunk, dtype=np.int16)

def dominant(frame_rate, chunk):
    w = np.fft.fft(chunk)
    freqs = np.fft.fftfreq(len(chunk))
    peak_coeff = np.argmax(np.abs(w))
    peak_freq = freqs[peak_coeff]
    return abs(peak_freq * frame_rate) # in Hz

def match(freq1, freq2):
    return abs(freq1 - freq2) < 20

def decode_bitchunks(chunk_bits, chunks):
    out_bytes = []

    next_read_chunk = 0
    next_read_bit = 0

    byte = 0
    bits_left = 8
    while next_read_chunk < len(chunks):
        can_fill = chunk_bits - next_read_bit
        to_fill = min(bits_left, can_fill)
        offset = chunk_bits - next_read_bit - to_fill
        byte <<= to_fill
        shifted = chunks[next_read_chunk] & (((1 << to_fill) - 1) << offset)
        byte |= shifted >> offset;
        bits_left -= to_fill
        next_read_bit += to_fill
        if bits_left <= 0:

            out_bytes.append(byte)
            byte = 0
            bits_left = 8

        if next_read_bit >= chunk_bits:
            next_read_chunk += 1
            next_read_bit -= chunk_bits

    return out_bytes

def decode_file(input_file, speed):
    wav = wave.open(input_file)
    if wav.getnchannels() == 2:
        mono = StringIO()
        stereo_to_mono(input_file, mono)

        mono.seek(0)
        input_file = mono
    wav.close()

    offset = 0
    for frame_rate, chunk in yield_chunks(input_file, speed / 2):
        dom = dominant(frame_rate, chunk)
        print("{} => {}".format(offset, dom))
        offset += 1

def extract_packet(freqs):
    freqs = freqs[::2]
    bit_chunks = [int(round((f - START_HZ) / STEP_HZ)) for f in freqs]
    print(bit_chunks)
    bit_chunks = [c for c in bit_chunks[1:] if 0 <= c < (2 ** BITS)]
    ID_INCLUDE = False
    bit_chunks = bit_chunks[:len(bit_chunks)-8]
    if len(bit_chunks)> MY_ID_LEN:
        for index_ in range(0,len(bit_chunks)):
            if bit_chunks[index_:index_+MY_ID_LEN] == MY_ID_LIST:
                ID_INCLUDE = True
                bit_chunks = bit_chunks[:index_]+bit_chunks[index_+MY_ID_LEN:]
                break
    #print(bit_chunks)
    return bytearray(decode_bitchunks(BITS, bit_chunks)),ID_INCLUDE,bit_chunks

def display(s):
    cprint(figlet_format(s.replace(' ', '   '), font='doom'), 'yellow')

def listen_linux(frame_rate=44100, interval=0.1):

    mic = alsaaudio.PCM(alsaaudio.PCM_CAPTURE, alsaaudio.PCM_NORMAL, device="default")
    mic.setchannels(1)
    mic.setrate(44100)
    mic.setformat(alsaaudio.PCM_FORMAT_S16_LE)

    num_frames = int(round((interval / 2) * frame_rate))
    mic.setperiodsize(num_frames)
    print("start...")

    in_packet = False
    packet = []

    while True:
        l, data = mic.read()
        #print(data)
        if not l:
            continue

        chunk = np.fromstring(data, dtype=np.int16)
        dom = dominant(frame_rate, chunk)

        if in_packet and match(dom, HANDSHAKE_END_HZ):
            byte_stream,pt,selected_pk = extract_packet(packet)
            print(byte_stream)
            #try:    
                #print(byte_stream)
            #byte_stream = RSCodec(FEC_BYTES).decode(byte_stream)
                #print(byte_stream)
            byte_stream = byte_stream.decode("utf-8")
                #print(byte_stream)
            if pt:
                display(byte_stream)
                make_sound(selected_pk)
            #except ReedSolomonError as e:
            #    pass
                #print("{}: {}".format(e, byte_stream))

            packet = []
            in_packet = False
        elif in_packet:
            packet.append(dom)
        elif match(dom, HANDSHAKE_START_HZ):
            in_packet = True

if __name__ == '__main__':
    colorama.init(strip=not sys.stdout.isatty())
    p = pyaudio.PyAudio()
    stream =p.open(format=pyaudio.paFloat32,channels=1,rate=44100,output=True)
    #decode_file(sys.argv[1], float(sys.argv[2]))
    listen_linux()
