không nhận python 3.10

@@ -70,7 +70,7 @@ function(do_build_boost version)
     if(c MATCHES "^python([0-9])\$")
       set(with_python_version "${CMAKE_MATCH_1}")
       list(APPEND boost_with_libs "python")
-    elseif(c MATCHES "^python([0-9])\\.?([0-9])\$")
+    elseif(c MATCHES "^python([0-9])\\.?([0-9]+)\$")
       set(with_python_version "${CMAKE_MATCH_1}.${CMAKE_MATCH_2}")
       list(APPEND boost_with_libs "python")
     else()
-- Building with ccache: /usr/bin/ccache, CCACHE_DIR=


#2

Đây là lỗi tương thích Boost 1.73 với Python đang dùng. Trên Ubuntu, sửa lời gọi _Py_fopen(f, "r") thành fopen(f, "r"); Boost mới hơn cũng đã chuyển sang dùng fopen. Source Boost 1.76.

Chạy tại VM ceph-dev để sửa đúng bản Boost đang được biên dịch:

cd /home/dangg/16.2.5/ceph

python3 - <<'PY'
from pathlib import Path

p = Path("build/boost/src/Boost/libs/python/src/exec.cpp")
text = p.read_text()

old = 'FILE *fs = _Py_fopen(f, "r");'
new = 'FILE *fs = fopen(f, "r");'

if text.count(old) != 1:
    raise SystemExit("Không tìm thấy đúng dòng cần sửa; chưa thay đổi file.")

backup = p.with_name("exec.cpp.before-fopen-fix")
if not backup.exists():
    backup.write_text(text)

p.write_text(text.replace(old, new, 1))
print("Đã sửa _Py_fopen thành fopen.")
PY

Khi script báo sửa thành công, tiếp tục build trên thư mục hiện tại: