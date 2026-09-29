# 08 — cephadm/orchestrator, lifecycle và upgrade workflow: v16.2.15 → v17.2.7

**Trạng thái: đang phân tích.** [CSV đầy đủ của owner](./08-cephadm-orchestrator.csv) có 134 hàng, là subset theo thứ tự của [master inventory](./00-file-inventory.csv). Hiện `affect = 1`, `trivial = 0`, **chưa phân loại = 133**; các số 0 không phải kết luận không có tác động.

## Phạm vi và phương pháp

Owner này phụ trách cephadm/orchestrator, lifecycle và upgrade workflow. Nguồn là endpoint net diff của `v16.2.15` (`618f440892089921c3e944a991122ddc44e60516`) và `v17.2.7` (`b12291d110049b2f35e32e0de30d70e9a4c060d2`) trong cùng repo `ceph16.2.15/ceph`. Hai tag ở hai release branch, nên base không phải ancestor của target. Priority trong CSV là thứ tự đọc, không phải rủi ro.

## Findings liên quan nâng cấp

### ADM-001 — Offline host làm upgrade dừng với health signal riêng

**CSV:** `src/pybind/mgr/cephadm/upgrade.py`. Base `_do_upgrade()` chưa kiểm `offline_hosts` ở đầu và `upgrade_tick()` bắt lỗi chung; target kiểm tập offline trước khi tiến hành, ném `HostConnectionError` và `upgrade_tick()` chuyển thành `UPGRADE_OFFLINE_HOST` với host/address. `upgrade_resume()` còn xóa upgrade health warning cũ. Commit liên quan `3787501849be5a9ce72c3df2f9ad536e21780684`, `a5f6cdef4bce7295a8a1f7a032ae92fca0ae52cf`. `src/pybind/mgr/cephadm/tests/test_upgrade.py` có tests start/do-upgrade khi host offline và resume warning; đã đọc nhưng chưa chạy.

**Điều kiện:** cluster dùng cephadm và host được đánh dấu offline hoặc SSH lỗi trong lúc rollout. Trong mixed-version MGR Pacific điều phối theo đường cũ; khi MGR target active, lỗi có signal riêng và upgrade dừng sớm để operator xử lý host. Sau full upgrade behavior target đồng nhất. Không tự suy host offline có hay không từ repo. **Evidence confidence:** high cho code/test, medium cho applicability cluster. **Kiểm chứng:** trong lab có host giả lập offline, xác nhận `UPGRADE_OFFLINE_HOST`, trạng thái pause/fail và `resume` sau khi khôi phục kết nối; quan sát `ceph orch upgrade status`, health, host cache. Không gây mất kết nối production để thử.

### ADM-002 — Cách xác định daemon đã ở target image phụ thuộc `use_repo_digest`

**CSV:** cùng `upgrade.py`. Base `_detect_need_upgrade()` so container digest với target digest. Target phân nhánh: khi `use_repo_digest=true` (default ở hai endpoint), so digest; khi false, so `container_image_name` với target name. `target_image` cũng trả digest hoặc name theo option. Commit `bf8820d449d1076fd3b0fb4c10c50823ed4d0f85`. `test_upgrade_run` trong `tests/test_upgrade.py` parametrizes cả hai giá trị option, nhưng chưa chạy trên môi trường này.

**Điều kiện:** cephadm upgrade và option `use_repo_digest` được đặt; đặc biệt nếu false, tag/name có thể là mutable, vì vậy kết quả `need_upgrade`/completion dựa theo tên chứ không xác minh nội dung qua digest ở nhánh đó. Trong mixed rollout active MGR phiên bản khác nhau có thể phân loại daemon theo logic khác; sau full target MGR logic theo option target. **Evidence confidence:** high cho branch code, medium cho artifact thực tế. **Kiểm chứng:** pin target artifact bằng digest khi cần tính tái lập; trong lab so `ceph orch ps` image name, repo digest, deployed_by trên từng cohort và trạng thái complete theo cả hai mode. Không kết luận image là đúng chỉ từ tag trùng.

**Cross-reference:** cephadm sau OSD phase có `_complete_osd_upgrade` gọi `osd require-osd-release`; guard/rollback checkpoint thuộc [MON-001](./04-mon-osdmap-crush.md). Method này có ở cả hai endpoint, nên không dùng nó làm bằng chứng riêng cho một hunk `upgrade.py`.

Các hàng khác vẫn để trống `upgrade_impact` cho tới khi đọc diff/metadata; không gán `trivial` theo đường dẫn.

## Kiểm chứng cần hoàn thành

- Đọc hunk và context cho các cụm hành vi trong owner; xét riêng khác biệt mixed-version, full-version, rollback và activation.
- Đối chiếu commit, test repository và tài liệu chính thức khi claim cần xác minh thêm.
- Gắn từng hàng `affect|trivial` cùng lý do; mỗi `affect` phải trỏ tới finding ID có mô tả trước/sau, applicability, confidence và kịch bản validation.
- Chỉ sau khi binary gate hoàn tất mới đối soát `affect + trivial = 134` và viết tóm tắt các cụm trivial.

## Giới hạn hiện tại

Chưa có As-Is cluster hoặc lab/canary cho cặp endpoint. Không đưa GO/NO-GO production từ báo cáo đang phân tích này.
