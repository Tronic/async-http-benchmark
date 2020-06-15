import os
import signal
import subprocess
import sys
import time
from socket import socket, AF_INET, SOCK_STREAM

code, mimetype, body = 200, b"text/plain", b"Hello, World!"
response = b"HTTP/1.1 %d\r\ncontent-type: %b;charset=utf-8\r\ncontent-length: %d\r\n\r\n%b" % (code, mimetype, len(body), body)

def asyncio_sockets(server_sock):
    import asyncio
    loop = asyncio.get_event_loop()

    async def httpserve(sock):
        data = bytearray()
        try:
            while True:
                d = await loop.sock_recv(sock, 2048)
                if not d: break
                data += d
                pos = data.find(b"\r\n\r\n", max(0, len(data) - len(d) - 3))
                if pos > -1:
                    del data[:pos + 4]
                    await loop.sock_sendall(sock, response)
        except OSError:
            pass
        finally:
            sock.close()

    async def runserver():
        tasks = []
        try:
            while True:
                sock, addr = await loop.sock_accept(server_sock)
                tasks.append(loop.create_task(httpserve(sock)))
        finally:
            for t in tasks:
                try:
                    await t
                except KeyboardInterrupt:
                    pass

    loop.run_until_complete(runserver())

def asyncio_streams(server_sock):
    import asyncio

    async def httpserve(reader, writer):
        data = bytearray()
        try:
            async for d in reader:
                data += d
                pos = data.find(b"\r\n\r\n", max(0, len(data) - len(d) - 3))
                if pos > -1:
                    del data[:pos + 4]
                    writer.write(response)
        except OSError:
            pass
        finally:
            writer.close()

    async def runserver():
        # Note: asyncio already supports "with server" but uvloop doesn't
        server = await asyncio.start_server(httpserve, sock=server_sock)
        try:
            await server.serve_forever()
        finally:
            server.close()

    asyncio.run(runserver())

def uvloop_sockets(server_sock):
    import uvloop
    uvloop.install()
    asyncio_sockets(server_sock)

def uvloop_streams(server_sock):
    import uvloop
    uvloop.install()
    asyncio_streams(server_sock)

def trio_sockets(server_sock):
    import trio

    async def runserver(server_sock):
        async with trio.open_nursery() as nursery:
            while True:
                sock, addr = await server_sock.accept()
                nursery.start_soon(httpserve, sock)

    async def httpserve(sock):
        data = bytearray()
        try:
            while True:
                d = await sock.recv(2048)
                if not d: break
                data += d
                pos = data.find(b"\r\n\r\n", max(0, len(data) - len(d) - 3))
                if pos > -1:
                    del data[:pos + 4]
                    pos = 0
                    while pos < len(response):
                        pos += await sock.send(response[pos:])
        except OSError:
            pass
        finally:
            sock.close()

    trio.run(runserver, trio.socket.from_stdlib_socket(server_sock))

def trio_streams(server_sock):
    import trio

    async def httpserve(stream):
        async with stream:
            data = bytearray()
            try:
                async for d in stream:
                    data += d
                    pos = data.find(b"\r\n\r\n", max(0, len(data) - len(d) - 3))
                    if pos > -1:
                        del data[:pos + 4]
                        await stream.send_all(response)
            except trio.BrokenResourceError:
                pass

    # Streams API requires some trickery to use stdlib socket
    server_sock = trio.socket.from_stdlib_socket(server_sock)
    listeners = trio.SocketListener(server_sock),
    trio.run(trio.serve_listeners, httpserve, listeners)

tests = {t.__name__: t for t in (
    asyncio_sockets, asyncio_streams,
    uvloop_sockets, uvloop_streams,
    trio_sockets, trio_streams,
)}

def main():
    os.setpgrp()
    for test, testfunc in tests.items():
        if len(sys.argv) > 1 and sys.argv[1] not in test: continue
        with socket(AF_INET, SOCK_STREAM) as server_sock:
            server_sock.bind(("127.0.0.1", 0))
            server_sock.listen(100)
            server_sock.setblocking(False)
            server_sock.set_inheritable(True)
            ip, port = server_sock.getsockname()
            url = f'http://{ip}:{port}/'
            workers = 8
            command = 'wrk', '--latency', '-t8', '-c100', url
            print(f"{test} >>> {' '.join(command)}")
            for i in range(workers):
                pid = os.fork()
                if not pid:
                    # Run test server
                    try: tests[test](server_sock)
                    except Exception as e:
                        # Only the first worker shows errors here
                        if i == 0: sys.stderr.write(f"{e!r}\n")
                    finally: return  # End worker process!
        try:
            print("Sleeping 1s to let the server start...")
            time.sleep(1)
            subprocess.call(command)
        except Exception as e:
            print(f"Test failed: {e}")
            input("Press ENTER to kill server and continue!")
        finally:
            # KeyboardInterrupt workers & cooldown between tests
            for i in range(3):
                try: os.killpg(0, signal.SIGINT)
                except KeyboardInterrupt: pass
                time.sleep(0.5)
            print()

main()
