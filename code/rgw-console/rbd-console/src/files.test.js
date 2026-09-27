import test from "node:test";
import assert from "node:assert/strict";
import { Readable } from "node:stream";
import { normalizeVolumePath, SftpFileService, sniffMime } from "./files.js";
import { TerminalTicketStore } from "./terminal.js";

test("SFTP logical paths preserve safe names and reject traversal/control characters", () => {
  assert.deepEqual(normalizeVolumePath("/photos/a b.jpg"), {
    logical: "/photos/a b.jpg",
    segments: ["photos", "a b.jpg"],
  });
  assert.throws(() => normalizeVolumePath("/photos/../escape"), error => error.code === "PATH_ESCAPE");
  assert.throws(() => normalizeVolumePath("/photos\\escape"), error => error.code === "INVALID_PATH");
  assert.throws(() => normalizeVolumePath("/bad\0name"), error => error.code === "INVALID_PATH");
});

test("preview MIME sniffing does not trust a filename extension", () => {
  assert.equal(sniffMime("fake.txt", Buffer.from([0, 1, 2, 3])), "application/octet-stream");
  assert.equal(sniffMime("fake.txt", Buffer.from([0xc3, 0x28])), "application/octet-stream");
  assert.equal(sniffMime("wrong.txt", Buffer.from([0xff, 0xd8, 0xff, 0xdb])), "image/jpeg");
  assert.equal(sniffMime("payload.html", Buffer.from("<script>alert(1)</script>")), "text/plain");
  assert.equal(sniffMime("vector.bin", Buffer.from("<svg viewBox='0 0 1 1'></svg>")), "image/svg+xml");
  assert.equal(sniffMime("report.bin", Buffer.from("%PDF-1.7\n")), "application/pdf");
});

test("SFTP deletion rejects a non-empty directory with a stable domain error", async () => {
  let rmdirCalled = false;
  const directoryAttrs = {
    isDirectory: () => true,
    isFile: () => false,
    isSymbolicLink: () => false,
    size: 4096,
  };
  const sftp = {
    realpath(path, callback) { callback(null, path); },
    lstat(_path, callback) { callback(null, directoryAttrs); },
    readdir(_path, callback) { callback(null, [{ filename: "child.txt", attrs: directoryAttrs }]); },
    rmdir(_path, callback) { rmdirCalled = true; callback(null); },
    end() {},
  };
  const files = new SftpFileService({ openSftp: async () => sftp });
  await assert.rejects(
    files.remove("/mnt/rbd/volume", "/nonempty"),
    error => error.code === "DIRECTORY_NOT_EMPTY" && error.status === 409,
  );
  assert.equal(rmdirCalled, false);
});

test("SFTP checksum waits for the read stream pipeline and hashes every chunk", async () => {
  const files = new SftpFileService({});
  const sha256 = await files.hashResolved(
    { createReadStream: () => Readable.from([Buffer.from("live-"), Buffer.from("checksum")]) },
    { path: "/volume/file.txt", attrs: { isFile: () => true } },
  );
  assert.equal(sha256, "33afe780793317924bb7703e1a3efb31c6b07f088db2cd1d8868a1ced1001d2d");
});

test("terminal tickets are opaque, single-use and expire", async () => {
  const store = new TerminalTicketStore({ ttlMs: 10 });
  const issued = store.issue({ volume_id: "volume-1" });
  assert.match(issued.ticket, /^[A-Za-z0-9_-]{32,}$/);
  assert.deepEqual(store.consume(issued.ticket), { volume_id: "volume-1" });
  assert.throws(() => store.consume(issued.ticket), error => error.code === "TERMINAL_TICKET_INVALID");
  const expiring = store.issue({ volume_id: "volume-2" });
  await new Promise(resolve => setTimeout(resolve, 15));
  assert.throws(() => store.consume(expiring.ticket), error => error.code === "TERMINAL_TICKET_INVALID");
});
