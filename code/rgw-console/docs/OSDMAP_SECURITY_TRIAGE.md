# Đối chiếu bảo mật worker OSDMap tối giản

Ngày đối chiếu: **13/10/2026, UTC+7**. Đây là báo cáo bằng chứng, **không phải chấp thuận production, waiver, VEX do console phát hành hoặc cấu hình suppress**.

Artifact được kiểm: `storage-lab-osdmap:16.2.15-minimal-preview.1`, index `sha256:452ba2b9b3e4c1660b5e1e89a45b0d2a8aba6190d4d0bfa84d058403b147cff5`. Scout gốc vẫn giữ **1 Critical, 28 High, 40 Medium, 6 Low**. Không sửa, lọc hoặc thay thế [báo cáo Scout gốc](../deploy/dist/minimal-worker-preview-20261013/worker-vulnerabilities.md).

Kết quả đối chiếu 29 dòng Critical/High với nguồn chính thức: **15 vendor-fixed theo EVR; 5 vendor-not-affected; 4 CNA-rejected; 5 vendor-affected**. Đây là phân loại bằng chứng bổ sung, không đổi số đếm Scout hay biến image thành một release sạch CVE. Medium/Low, component Ceph được copy, mức độ khai thác thực và các release khác chưa được kết luận bởi bảng này.

## Cách kiểm và phạm vi nguồn

- Installed headers đọc từ RPM database thật trong đúng image bằng `rpm -q --qf '%{NAME}|%{EPOCHNUM}|%{VERSION}|%{RELEASE}|%{ARCH}|%{SOURCERPM}\n' ...`.
- Vendor records lấy từ `https://access.redhat.com/hydra/rest/securitydata/cve/<CVE>.json`; chỉ nhận `product_name` **chính xác** là `Red Hat Enterprise Linux 8`. Không dùng trạng thái của RHEL 9/10, SAP, EUS/AUS/TUS hay một component có tên tương tự để chứng minh cho UBI 8.
- Package trong Scout có thể là **source package**; binary `openssl-libs`, `libacl`, `libattr`, `libnghttp2`, `sqlite-libs` được ghép qua `SOURCERPM`, không so tên gần giống.
- Các dòng fixed đã kiểm epoch riêng bằng số nguyên, rồi version và release bằng `rpm.vercmp` của RPM Lua trong chính image. Kết quả `+1` nghĩa là installed mới hơn fixed; `0` nghĩa là bằng fixed. **Không dùng so chuỗi lexical.** Tất cả các cặp fixed ở bảng có cùng epoch; không bỏ qua epoch `1` của OpenSSL.
- CNA record lấy trực tiếp từ CVE Services API `https://cveawg.mitre.org/api/cve/<CVE>`. Bốn SQLite record được MITRE chuyển sang `REJECTED` ngày 31/07/2026. Red Hat API cho bốn record này trả 404; không coi 404 đơn lẻ là bằng chứng an toàn.
- Thuật ngữ **vendor-fixed** ở đây chứng minh installed EVR đạt bản vá của đúng vendor/product/component. Thuật ngữ **vendor-not-affected** là kết luận trong vendor record cho đúng product/component. Cả hai đều không phải quyết định cho phép chạy production của dự án này.

Ví dụ so EVR có thể tái tạo (epoch 0 đã kiểm bằng header):

```text
rpm --eval '%{lua: local c=rpm.vercmp("3.12.15","3.12.13"); if c==0 then c=rpm.vercmp("2.el8_10","2.el8_10") end; print(c)}'
```

## Installed headers và source package

Tất cả binary dưới đây là `x86_64`. Giá trị `0:` được ghi rõ dù RPM thường không in epoch 0 trong NEVRA.

| Binary package | Installed EVR | Source RPM thật |
|---|---|---|
| sqlite-libs | 0:3.26.0-21.el8_10 | sqlite-3.26.0-21.el8_10.src.rpm |
| python3.12; python3.12-libs | 0:3.12.15-2.el8_10 | python3.12-3.12.15-2.el8_10.src.rpm |
| gnutls | 0:3.6.16-8.el8_10.6 | gnutls-3.6.16-8.el8_10.6.src.rpm |
| gnupg2 | 0:2.2.20-4.el8_10 | gnupg2-2.2.20-4.el8_10.src.rpm |
| openssl-libs | 1:1.1.1k-17.el8_6 | openssl-1.1.1k-17.el8_6.src.rpm |
| pcre2 | 0:10.32-3.el8_6 | pcre2-10.32-3.el8_6.src.rpm |
| glibc | 0:2.28-251.el8_10.43 | glibc-2.28-251.el8_10.43.src.rpm |
| libarchive | 0:3.3.3-7.el8_10 | libarchive-3.3.3-7.el8_10.src.rpm |
| libacl | 0:2.4.0-1.el8_10 | acl-2.4.0-1.el8_10.src.rpm |
| brotli | 0:1.0.6-4.el8_10 | brotli-1.0.6-4.el8_10.src.rpm |
| libattr | 0:2.6.0-1.el8_10 | attr-2.6.0-1.el8_10.src.rpm |
| expat | 0:2.5.0-4.el8_10 | expat-2.5.0-4.el8_10.src.rpm |
| libnghttp2 | 0:1.33.0-6.el8_10.3 | nghttp2-1.33.0-6.el8_10.3.src.rpm |
| zlib | 0:1.2.11-25.el8 | zlib-1.2.11-25.el8.src.rpm |

## Matrix 29 CVE

Trong cột sản phẩm, **RHEL 8** luôn viết tắt cho `Red Hat Enterprise Linux 8` chính xác. Component sau dấu `/` là source component của vendor, được ghép với binary qua bảng header phía trên. Dấu `—` ở fixed EVR nghĩa là record không cấp bản vá phù hợp component này, **không** có nghĩa là đã an toàn. Mỗi link RH trỏ thẳng tới record JSON chính thức; mỗi link CNA trỏ thẳng tới record CVE chính thức. Tất cả đều được kiểm ngày **13/10/2026**.

| CVE / Scout | Source package; installed binary EVR | Sản phẩm / component; vendor state | Fixed EVR / advisory đúng stream | RPM compare | Kết luận bằng chứng | Nguồn |
|---|---|---|---|---|---|---|
| CVE-2026-51302 / Critical | sqlite; sqlite-libs 0:3.26.0-21.el8_10 | RH API 404; MITRE CNA `REJECTED` | — | — | CNA-rejected, cập nhật 31/07/2026 | [CNA](https://cveawg.mitre.org/api/cve/CVE-2026-51302) |
| CVE-2026-51304 / High | sqlite; sqlite-libs 0:3.26.0-21.el8_10 | RH API 404; MITRE CNA `REJECTED` | — | — | CNA-rejected, cập nhật 31/07/2026 | [CNA](https://cveawg.mitre.org/api/cve/CVE-2026-51304) |
| CVE-2026-51303 / High | sqlite; sqlite-libs 0:3.26.0-21.el8_10 | RH API 404; MITRE CNA `REJECTED` | — | — | CNA-rejected, cập nhật 31/07/2026 | [CNA](https://cveawg.mitre.org/api/cve/CVE-2026-51303) |
| CVE-2026-51297 / High | sqlite; sqlite-libs 0:3.26.0-21.el8_10 | RH API 404; MITRE CNA `REJECTED` | — | — | CNA-rejected, cập nhật 31/07/2026 | [CNA](https://cveawg.mitre.org/api/cve/CVE-2026-51297) |
| CVE-2026-51296 / High | sqlite; sqlite-libs 0:3.26.0-21.el8_10 | RHEL 8 / sqlite; `Not affected` | — | — | Vendor-not-affected | [RH](https://access.redhat.com/hydra/rest/securitydata/cve/CVE-2026-51296.json) |
| CVE-2026-6100 / High | python3.12; python3.12 0:3.12.15-2.el8_10 | RHEL 8 / python3.12; fixed release | 0:3.12.13-2.el8_10 / RHSA-2026:10950 | +1 | Vendor-fixed | [RH](https://access.redhat.com/hydra/rest/securitydata/cve/CVE-2026-6100.json) |
| CVE-2026-15308 / High | python3.12; python3.12 0:3.12.15-2.el8_10 | RHEL 8 / python3.12; fixed release | 0:3.12.13-3.el8_10 / RHSA-2026:39893 | +1 | Vendor-fixed | [RH](https://access.redhat.com/hydra/rest/securitydata/cve/CVE-2026-15308.json) |
| CVE-2026-19553 / High | python3.12; python3.12 0:3.12.15-2.el8_10 | RHEL 8 / python3.12; fixed release | 0:3.12.15-2.el8_10 / RHSA-2026:77028 | 0 | Vendor-fixed | [RH](https://access.redhat.com/hydra/rest/securitydata/cve/CVE-2026-19553.json) |
| CVE-2026-4786 / High | python3.12; python3.12 0:3.12.15-2.el8_10 | RHEL 8 / python3.12; fixed release | 0:3.12.13-2.el8_10 / RHSA-2026:10950 | +1 | Vendor-fixed | [RH](https://access.redhat.com/hydra/rest/securitydata/cve/CVE-2026-4786.json) |
| CVE-2026-4519 / High | python3.12; python3.12 0:3.12.15-2.el8_10 | RHEL 8 / python3.12; fixed release | 0:3.12.12-4.el8_10 / RHSA-2026:6283 | +1 | Vendor-fixed | [RH](https://access.redhat.com/hydra/rest/securitydata/cve/CVE-2026-4519.json) |
| CVE-2026-33846 / High | gnutls; gnutls 0:3.6.16-8.el8_10.6 | RHEL 8 / gnutls; fixed release | 0:3.6.16-8.el8_10.6 / RHSA-2026:20611 | 0 | Vendor-fixed | [RH](https://access.redhat.com/hydra/rest/securitydata/cve/CVE-2026-33846.json) |
| CVE-2026-33845 / High | gnutls; gnutls 0:3.6.16-8.el8_10.6 | RHEL 8 / gnutls; fixed release | 0:3.6.16-8.el8_10.6 / RHSA-2026:20611 | 0 | Vendor-fixed | [RH](https://access.redhat.com/hydra/rest/securitydata/cve/CVE-2026-33845.json) |
| CVE-2026-88648 / High | gnutls; gnutls 0:3.6.16-8.el8_10.6 | RHEL 8 / gnutls; `Affected` | — | — | Affected; chưa xác minh bản vá khả dụng | [RH](https://access.redhat.com/hydra/rest/securitydata/cve/CVE-2026-88648.json) |
| CVE-2026-88647 / High | gnutls; gnutls 0:3.6.16-8.el8_10.6 | RHEL 8 / gnutls; `Affected` | — | — | Affected; chưa xác minh bản vá khả dụng | [RH](https://access.redhat.com/hydra/rest/securitydata/cve/CVE-2026-88647.json) |
| CVE-2026-24882 / High | gnupg2; gnupg2 0:2.2.20-4.el8_10 | RHEL 8 / gnupg2; `Not affected` | — | — | Vendor-not-affected | [RH](https://access.redhat.com/hydra/rest/securitydata/cve/CVE-2026-24882.json) |
| CVE-2026-24881 / High | gnupg2; gnupg2 0:2.2.20-4.el8_10 | RHEL 8 / gnupg2; `Not affected` | — | — | Vendor-not-affected | [RH](https://access.redhat.com/hydra/rest/securitydata/cve/CVE-2026-24881.json) |
| CVE-2025-68973 / High | gnupg2; gnupg2 0:2.2.20-4.el8_10 | RHEL 8 / gnupg2; fixed release | 0:2.2.20-4.el8_10 / RHSA-2026:0728 | 0 | Vendor-fixed | [RH](https://access.redhat.com/hydra/rest/securitydata/cve/CVE-2025-68973.json) |
| CVE-2026-45447 / High | openssl; openssl-libs 1:1.1.1k-17.el8_6 | RHEL 8 / openssl; fixed release | 1:1.1.1k-16.el8_6 / RHSA-2026:26275 | +1 | Vendor-fixed | [RH](https://access.redhat.com/hydra/rest/securitydata/cve/CVE-2026-45447.json) |
| CVE-2026-84782 / High | openssl; openssl-libs 1:1.1.1k-17.el8_6 | RHEL 8 / openssl; `Affected` | —; compat-openssl10 fix **không dùng** cho openssl-libs 1.1 | — | Affected; chưa xác minh bản vá phù hợp | [RH](https://access.redhat.com/hydra/rest/securitydata/cve/CVE-2026-84782.json) |
| CVE-2026-103111 / High | pcre2; pcre2 0:10.32-3.el8_6 | RHEL 8 / pcre2; `Affected` | — | — | Affected; chưa xác minh bản vá khả dụng | [RH](https://access.redhat.com/hydra/rest/securitydata/cve/CVE-2026-103111.json) |
| CVE-2026-89161 / High | pcre2; pcre2 0:10.32-3.el8_6 | RHEL 8 / pcre2; `Not affected` | — | — | Vendor-not-affected; không dùng state của mariadb | [RH](https://access.redhat.com/hydra/rest/securitydata/cve/CVE-2026-89161.json) |
| CVE-2026-4046 / High | glibc; glibc 0:2.28-251.el8_10.43 | RHEL 8 / glibc; fixed release | 0:2.28-251.el8_10.37 / RHSA-2026:20587 | +1 | Vendor-fixed; RH severity Moderate | [RH](https://access.redhat.com/hydra/rest/securitydata/cve/CVE-2026-4046.json) |
| CVE-2026-4424 / High | libarchive; libarchive 0:3.3.3-7.el8_10 | RHEL 8 / libarchive; fixed release | 0:3.3.3-7.el8_10 / RHSA-2026:8534 | 0 | Vendor-fixed | [RH](https://access.redhat.com/hydra/rest/securitydata/cve/CVE-2026-4424.json) |
| CVE-2026-54369 / High | acl; libacl 0:2.4.0-1.el8_10 | RHEL 8 / acl; fixed release | 0:2.4.0-1.el8_10 / RHSA-2026:43420 | 0 | Vendor-fixed | [RH](https://access.redhat.com/hydra/rest/securitydata/cve/CVE-2026-54369.json) |
| CVE-2025-6176 / High | brotli; brotli 0:1.0.6-4.el8_10 | RHEL 8 / brotli; fixed release | 0:1.0.6-4.el8_10 / RHSA-2026:2389 | 0 | Vendor-fixed | [RH](https://access.redhat.com/hydra/rest/securitydata/cve/CVE-2025-6176.json) |
| CVE-2026-54371 / High | attr; libattr 0:2.6.0-1.el8_10 | RHEL 8 / attr; fixed release | 0:2.6.0-1.el8_10 / RHSA-2026:56133 | 0 | Vendor-fixed; RH severity Moderate | [RH](https://access.redhat.com/hydra/rest/securitydata/cve/CVE-2026-54371.json) |
| CVE-2026-77214 / High | expat; expat 0:2.5.0-4.el8_10 | RHEL 8 / expat; `Affected` | — | — | Affected; chưa xác minh bản vá khả dụng | [RH](https://access.redhat.com/hydra/rest/securitydata/cve/CVE-2026-77214.json) |
| CVE-2026-27135 / High | nghttp2; libnghttp2 0:1.33.0-6.el8_10.3 | RHEL 8 / nghttp2; fixed release | 0:1.33.0-6.el8_10.2 / RHSA-2026:7667 | +1 | Vendor-fixed; không dùng bản vá nodejs | [RH](https://access.redhat.com/hydra/rest/securitydata/cve/CVE-2026-27135.json) |
| CVE-2026-22184 / High | zlib; zlib 0:1.2.11-25.el8 | RHEL 8 / zlib; `Not affected` | — | — | Vendor-not-affected | [RH](https://access.redhat.com/hydra/rest/securitydata/cve/CVE-2026-22184.json) |

Không có dòng **unresolved/review-pending** còn lại trong phân loại 29 record ở thời điểm đối chiếu: bốn trường hợp RH API 404 đã có bằng chứng CNA-rejected riêng. Điều này **không** kết luận mọi CVE hoặc mọi đường thực thi trong image đã được xử lý.

## Package nào bắt buộc, package nào có thể loại bỏ

[Manifest closure thật](../deploy/dist/minimal-worker-preview-20261013/dependency-closure.json) ghi 22 ELF dependency entries và 114 RPM headers tại build. Ba ELF Ceph giữ nguyên SHA-256: osdmaptool `c1532cfd43e6a0cfab5c6a3bd3da405ac7224606646f9351fe34bf5fb2ed1fe0`, crushtool `187ab0d81224f4e692a4376b728a86f380dffa599529bd7b9749389a086952ce`, libceph-common `e6a4768ebf2e3836c7d38258840b27620bb0ea6bf1070fe90be635ce899462b9`.

| Nhóm | Bằng chứng / giới hạn |
|---|---|
| OpenSSL, PCRE2, glibc, zlib | Có trong ldd closure của tool/Ceph library. Không gỡ được để làm sạch số scan mà giữ nguyên binary/ABI. OpenSSL84782 và PCRE2103111 vẫn vendor-affected. |
| Python 3.12 | Interpreter bắt buộc cho worker. Năm High của source package đã đạt fixed EVR nhưng raw Scout vẫn ghi High. |
| SQLite, Expat | Worker không gọi SQL/XML; tuy nhiên Python3.12-libs RPM thật requires `libsqlite3.so.0` và `libexpat.so.1`. Ép gỡ bằng `--nodeps` hoặc xóa file nhưng giữ registration là không hợp lệ. Expat77214 còn vendor-affected. |
| GnuTLS, GnuPG, libarchive, curl/nghttp2/Brotli, GLib2/libdnf/librepo | Không có trong tool ELF closure; chủ yếu phục vụ package-manager/base utilities. Có thể thử **genuine solver uninstall** một tập đóng phụ thuộc, nhưng chưa được coi là loại bỏ an toàn cho đến khi solver không kéo core, RPM query/DB và `/bin/chown` còn dùng được, đủ fixture qua. |
| ACL, Attr | Worker không gọi trực tiếp, nhưng `/bin/chown` của coreutils-single và RPM cần thư viện này. Phải giữ init-volume workflow và metadata thật; không gỡ mù quáng. Các High tương ứng đã đạt vendor-fixed EVR. |

Repo query từ public UBI repositories ngày 13/10/2026 trả glibc `2.28-251.el8_10.48` mới hơn `.43` đã build; các package trong bảng khác vẫn cùng EVR đã cài. Có thể update glibc qua package manager thật và nghiệm thu lại, nhưng không dùng cập nhật này để giải quyết năm vendor-affected còn lại khi chưa có fixed EVR phù hợp. Repositories queried: UBI 8 BaseOS/AppStream public, không subscription secret hay repository bên thứ ba.

## Hướng tiếp theo, chưa thực hiện bởi báo cáo

1. Giữ nguyên raw Scout và báo cáo này song song; có thể gửi phản hồi dữ liệu scanner cho các dòng vendor-fixed/not-affected/rejected, không tự biến chúng thành suppression.
2. Thử transaction solver trong container tạm để gỡ package-manager extras. Không `--nodeps`, không fake RPM DB, không xóa library/source files nhằm che catalog. Không kéo Python/tool/closure/RPM query/DB/chown ra khỏi runtime.
3. Nếu đạt, tạo một **tag thử nghiệm mới** và scan toàn artifact, kể cả Ceph component SBOM, rồi chạy lại cùng fixture. Không ghi đè preview.1, RC1 hoặc deployment hiện có.
4. OpenSSL/PCRE2/Expat affected vẫn là giới hạn thật cần vendor fix hoặc một runtime/adapter mới được kiểm chứng. Không tự giả OpenSSL 3 là `libcrypto.so.1.1`; thay/rebuild Ceph binary làm mất pin hiện tại và cần capability/fixture mới.

Quyết định production vẫn **chưa được phê duyệt**. Network-none/UID thấp/readonly rootfs là giảm phạm vi ảnh hưởng, không thay thế bản vá hay làm biến mất CVE.

## Thử gỡ package-manager extras trong container tạm

Đã thử ngày 13/10/2026 sau khi đối chiếu matrix. **Không build/tag/push image mới, không đổi Dockerfile hoặc deployment**. Container tạo từ đúng preview.1, `network=none`, không mount key/secret, chỉ bind source test ở chế độ read-only, tự xóa khi hoàn tất.

Dry-run dùng `microdnf --disablerepo='*' --assumeno remove ...`; solver đề xuất đúng 13 package, không thêm package core nào và kết thúc `Operation aborted`. Sau đó thử transaction thật trong **một container tạm khác**, không `--nodeps`, không force, không xóa file thủ công:

```text
microdnf --disablerepo='*' -y remove microdnf libdnf librepo librhsm libpeas gobject-introspection json-glib libmodulemd libsolv gpgme gnupg2 glib2 gnutls
```

| Package bị gỡ thật | Installed NEVR tại trial (epoch 0) |
|---|---|
| microdnf | 3.8.0-2.el8 |
| libdnf | 0.63.0-21.el8_10 |
| librepo | 1.14.2-5.el8 |
| librhsm | 0.0.3-5.el8 |
| libpeas | 1.22.0-6.el8 |
| gobject-introspection | 1.56.1-2.el8_10 |
| json-glib | 1.4.4-1.el8 |
| libmodulemd | 2.13.0-1.el8 |
| libsolv | 0.7.20-7.el8_10 |
| gpgme | 1.13.1-12.el8 |
| gnupg2 | 2.2.20-4.el8_10 |
| glib2 | 2.56.4-178.el8_10 |
| gnutls | 3.6.16-8.el8_10.6 |

Kiểm sau transaction:

- RPM query và database thật còn hoạt động; **101 RPM headers** thay vì 114. Không tạo giả đăng ký package Ceph.
- `rpm`, `rpm-libs`, `python3.12`, `python3.12-libs`, `coreutils-single`, `openssl-libs`, `pcre2`, `glibc`, `zlib` vẫn installed; thư viện Ceph và hai tool vẫn đủ ba SHA-256 pin phía trên.
- Build verifier chạy lại thành công: **3 ELF hashes, 22 closure entries**; manifest trong container tạm được tạo lại từ inventory thật sau uninstall, không giữ inventory trước transaction rồi gọi là inventory hiện tại.
- `/bin/chown` chạy được; thư mục tạm chuyển owner/group thành `10001:10001`. `libacl`/`libattr` vẫn phải giữ cho coreutils/RPM.
- Cùng **17 worker tests** qua, `failures=0`, `errors=0`, sau khi test process chuyển thực sang **UID/GID 10001**. Có fixture tool thật, pin library, startup/capability, PG scope/parser, upmap giữ nguyên, expired job và symlink isolation.
- Python/RPM còn cần SQLite/Expat; tool closure còn cần OpenSSL/PCRE2. Ba vendor-affected tương ứng chưa được giải quyết bởi transaction này. `libarchive`, curl/nghttp2/Brotli cũng còn bởi phụ thuộc của RPM/curl; không tự gỡ những package đó ngoài thử nghiệm đã kiểm.

Đây là bằng chứng để cân nhắc một Dockerfile/tag thử nghiệm mới. **Chưa có scan artifact mới**; không trừ số CVE khỏi raw Scout của preview.1 hoặc tuyên bố trial làm image đạt gate production. Container trial đã bị loại bỏ; image preview.1/RC1 trên máy giữ nguyên.
