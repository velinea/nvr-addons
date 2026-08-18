import argparse
import hashlib
import os
import re
import struct
import sys
import threading
from http.server import BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from http.server import HTTPServer
from time import perf_counter

import librtmp
from librtmp.exceptions import RTMPTimeoutError
from librtmp.packet import PACKET_TYPE_VIDEO, PACKET_TYPE_AUDIO

ANNEX_B = b"\x00\x00\x00\x01"

t0 = perf_counter()

def log(msg):
    print(f"{perf_counter()-t0:8.3f} {msg}", file=sys.stderr)

USER = os.environ.get("NVR_USER", "admin")
PASS = os.environ.get("NVR_PASS", "Mannikko19")
NVR_HOST = os.environ.get("NVR_HOST", "192.168.1.250")
NVR_PORT = int(os.environ.get("NVR_PORT", "80"))

flv_header_written = False
output = None
clients = []
clients_lock = threading.Lock()
h264_mode = False
stream_name = "ch0_1.264"


def parse_avc_decoder_config(data):
    if len(data) < 7:
        return []
    version = data[0]
    if version != 1:
        return []
    nalu_length_size = (data[4] & 0x03) + 1
    num_sps = data[5] & 0x1F
    off = 6
    sps_list = []
    for _ in range(num_sps):
        if off + 2 > len(data):
            break
        sps_len = struct.unpack_from(">H", data, off)[0]
        off += 2
        if off + sps_len > len(data):
            break
        sps_list.append(data[off:off + sps_len])
        off += sps_len
    if off >= len(data):
        return sps_list
    num_pps = data[off]
    off += 1
    pps_list = []
    for _ in range(num_pps):
        if off + 2 > len(data):
            break
        pps_len = struct.unpack_from(">H", data, off)[0]
        off += 2
        if off + pps_len > len(data):
            break
        pps_list.append(data[off:off + pps_len])
        off += pps_len
    result = []
    for sps in sps_list:
        result.append(ANNEX_B + sps)
    for pps in pps_list:
        result.append(ANNEX_B + pps)
    return result


def avc_to_annexb(body):
    if len(body) < 5:
        return b""
    packet_type = body[1]
    if packet_type == 0:
        return b"".join(parse_avc_decoder_config(body[5:]))
    if packet_type == 1:
        nalu_length_size = 4
        data = body[5:]
        out = []
        off = 0
        while off + nalu_length_size <= len(data):
            nalu_len = struct.unpack_from(">I", data, off)[0]
            off += nalu_length_size
            if off + nalu_len > len(data):
                break
            out.append(ANNEX_B + data[off:off + nalu_len])
            off += nalu_len
        return b"".join(out)
    return b""


def write_flv(data):
    global flv_header_written, output
    if not flv_header_written:
        hdr = b"FLV\x01\x05" + struct.pack(">II", 9, 0)
        if output:
            output.write(hdr)
            output.flush()
        with clients_lock:
            for c in clients:
                try:
                    c.write(hdr)
                except Exception:
                    pass
        flv_header_written = True
    if output:
        output.write(data)
        output.flush()
    with clients_lock:
        dead = []
        for c in clients:
            try:
                c.write(data)
            except Exception:
                dead.append(c)
        for c in dead:
            clients.remove(c)


def on_result(*args):
    global authenticated

    if authenticated:
        return

    if not args:
        return

    obj = args[0]
    if not isinstance(obj, dict):
        return

    desc = obj.get("description", "")

    m = re.search(r"challenge=([0-9a-f]+)", desc)
    if not m:
        return

    nonce = m.group(1)
    digest = hashlib.md5(f"{nonce}:{PASS}".encode()).hexdigest()

    log("Logging in...")
    authenticated = True

    login = conn.call(
        f"login?method=md5"
        f"&nonce={nonce}"
        f"&username={USER}"
        f"&digest={digest}"
    )
    result = login.result(timeout=5)
    log(f"Login: {result}")

    create_stream = conn.remote_method("createStream", block=True)
    stream_id = create_stream()
    log(f"Stream ID: {stream_id}")

    log(f"Playing {stream_name} ...")
    conn.call("play", stream_name, transaction_id=0)

    while conn.connected:
        try:
            packet = conn.read_packet()
        except RTMPTimeoutError:
            continue
        except Exception as e:
            log(f"Read error: {e}")
            break

        if packet.type in (PACKET_TYPE_VIDEO, PACKET_TYPE_AUDIO):
            if h264_mode and packet.type == PACKET_TYPE_VIDEO:
                body = bytes(packet.body)
                if len(body) >= 2 and (body[0] & 0x0F) == 7:
                    annex = avc_to_annexb(body)
                    if annex:
                        write_flv(annex)
            else:
                tag = flv_tag(packet.type, packet.timestamp, bytes(packet.body))
                write_flv(tag)
        else:
            try:
                conn.handle_packet(packet)
            except Exception:
                pass


def on_status(*args):
    log(f"onStatus: {args}")


class FLVHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        if h264_mode:
            self.send_header("Content-Type", "video/h264")
        else:
            self.send_header("Content-Type", "video/x-flv")
        self.send_header("Connection", "close")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        with clients_lock:
            if flv_header_written and not h264_mode:
                self.wfile.write(b"FLV\x01\x05" + struct.pack(">II", 9, 0))
            clients.append(self.wfile)
        try:
            while True:
                self.wfile.flush()
                self.rfile.read(1)
        except Exception:
            pass

    def log_message(self, format, *args):
        pass


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


def serve_http(port):
    server = ThreadedHTTPServer(("0.0.0.0", port), FLVHandler)
    log(f"HTTP-FLV server on http://0.0.0.0:{port}/")
    log("  VLC:  vlc http://localhost:{port}/")
    log("  ffplay: ffplay http://localhost:{port}/")
    server.serve_forever()


def parse_args():
    p = argparse.ArgumentParser(
        description="Read RTMP from NVR and output FLV stream"
    )
    p.add_argument(
        "--serve",
        type=int,
        metavar="PORT",
        nargs="?",
        const=8080,
        help="Start HTTP-FLV server on PORT (default 8080)",
    )
    p.add_argument(
        "--stdout",
        action="store_true",
        default=False,
        help="Write FLV to stdout (useful when --serve is also set)",
    )
    p.add_argument(
        "--flv",
        action="store_true",
        default=False,
        help="Output FLV instead of raw H.264 (default: H.264)",
    )
    p.add_argument(
        "-c", "--channel",
        type=int,
        default=0,
        metavar="N",
        help="Camera channel index, 0-3 (default: 0)",
    )
    p.add_argument(
        "-s", "--stream",
        choices=["main", "sub"],
        default="sub",
        help="Stream type: main or sub (default: sub)",
    )
    p.add_argument(
        "--nvr-host",
        default=None,
        help="NVR host (default: env NVR_HOST or 192.168.1.250)",
    )
    p.add_argument(
        "--nvr-port",
        type=int,
        default=None,
        help="NVR RTMP port (default: env NVR_PORT or 80)",
    )
    p.add_argument(
        "--nvr-user",
        default=None,
        help="NVR username (default: env NVR_USER or admin)",
    )
    p.add_argument(
        "--nvr-pass",
        default=None,
        help="NVR password (default: env NVR_PASS)",
    )
    p.add_argument(
        "--go2rtc",
        action="store_true",
        default=False,
        help="Print go2rtc.yaml stream config and exit",
    )
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()

    if args.go2rtc:
        cmd = f"python3 /config/connect.py -c {args.channel} -s {args.stream}"
        if args.nvr_host:
            cmd += f" --nvr-host {args.nvr_host}"
        if args.nvr_port:
            cmd += f" --nvr-port {args.nvr_port}"
        print(f"streams:")
        print(f"  cam{args.channel}_{args.stream}: exec:{cmd}#killsignal=15")
        sys.exit(0)

    if args.nvr_host:
        NVR_HOST = args.nvr_host
    if args.nvr_port:
        NVR_PORT = args.nvr_port
    if args.nvr_user:
        USER = args.nvr_user
    if args.nvr_pass:
        PASS = args.nvr_pass

    if not args.serve and not args.stdout:
        args.stdout = True

    h264_mode = not args.flv
    stream_name = f"ch{args.channel}_{0 if args.stream == 'main' else 1}.264"

    if args.stdout:
        output = sys.stdout.buffer
        if h264_mode:
            sys.stderr.write("Output: raw H.264 to stdout\n")
            sys.stderr.write("  e.g.  python connect.py | ffplay -f h264 -i pipe:0\n")
        else:
            sys.stderr.write("Output: FLV to stdout\n")
            sys.stderr.write("  e.g.  python connect.py --flv | ffplay -i pipe:0\n")

    if args.serve:
        t = threading.Thread(target=serve_http, args=(args.serve,), daemon=True)
        t.start()

    authenticated = False

    conn = librtmp.RTMP(
        f"rtmp://{NVR_HOST}:{NVR_PORT}",
        flashver="WIN 32,0,0,363",
        swfurl=f"http://{NVR_HOST}/JaViewer.swf?player_max=4",
        pageurl=f"http://{NVR_HOST}/view2.html",
    )

    conn.register_invoke_handler("_result", on_result)
    conn.register_invoke_handler("onStatus", on_status)

    log("Connecting to NVR...")
    conn.connect()

    while conn.connected:
        try:
            conn.process_packets(timeout=10)
        except RTMPTimeoutError:
            continue
