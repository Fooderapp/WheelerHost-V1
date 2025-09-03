# test_send_to_bridge.py
import socket, json, time, math
ep=("127.0.0.1",27700)
s=socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

t0=time.time()
while time.time()-t0<5:
    t=time.time()-t0
    lx=math.sin(t*2.0)         # sweep -1..1
    pkt={"lx":lx,"ly":0.0,"rt":80,"lt":0,"buttons":(1<<0)}  # A held, RT light
    s.sendto(json.dumps(pkt).encode("utf-8"), ep)
    time.sleep(0.02)
print("done")
