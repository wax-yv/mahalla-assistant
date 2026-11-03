import time, subprocess
from pathlib import Path
import pgserver

root = Path(__file__).resolve().parent.parent
pgdata = root / ".pgdata" / "postgres"
pgdata.parent.mkdir(parents=True, exist_ok=True)
server = pgserver.get_server(pgdata, cleanup_mode=None)
uri = server.get_uri()
(root / ".pgdata" / "uri.txt").write_text(uri + "\n")
print("PG URI:", uri, flush=True)
info = server.get_postmaster_info()
createdb = Path(pgserver.__file__).parent / "pginstall" / "bin" / "createdb"
subprocess.run([str(createdb), "-h", "127.0.0.1", "-p", str(info.port), "-U", "postgres", "mahalla"], check=False)
(root / ".pgdata" / "uri_mahalla.txt").write_text(server.get_uri("mahalla") + "\n")
while True:
    time.sleep(3600)
