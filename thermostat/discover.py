import socket
import asyncio

IP_ADDRESS = '239.255.255.250'
PORT = 1900
MESSAGE = """TYPE: WM-DISCOVER\r\nVERSION: 1.0\r\n\r\nservices: com.marvell.wm.system*\r\n\r\n""".encode('utf-8')

async def discover_thermostat():
    sock = socket.socket(
        socket.AF_INET, # family
        socket.SOCK_DGRAM, # type
        socket.IPPROTO_UDP, # proto
    )
    try:
        pass # TODO
    finally:
        try:
            sock.setsockopt(
                socket.SOL_IP,
                socket.IP_DROP_MEMBERSHIP,
                socket.inet_aton(IP_ADDRESS) + socket.inet_aton('0.0.0.0'),
            )
        except socket.error:
            pass
        sock.close()