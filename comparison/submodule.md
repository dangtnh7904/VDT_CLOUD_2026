PS D:\career\VDT\GD2\upgrade_Ceph\ceph16.2.15\ceph> git describe --tags --exact-match HEAD

>> git submodule status --cached
>> v16.2.15
>> -2d7d78b9cc52e8a9529d8cc2d2954c7d375d5dd7 ceph-erasure-code-corpus
>> -70228ed56466b4be8a9abff9024f69820f68f6d0 ceph-object-corpus
>> -f24ceec055ea236a093988237a9821d145f5f7c8 src/blkin
>> -fd6124c74da0801f23f9d324559d8b66fb83f533 src/c-ares
>> -bb99e93da00c3fe8c6b6a98520fb17cf64710ce7 src/civetweb
>> -603529a4e06ac8a1662c13d6b31f122e21830352 src/crypto/isa-l/isa-l_crypto
>> -9b1326cfa09735ae18b1c4c308ec424c5f1b9cce src/dmclock
>> -7e61b44404f0ed410c83cfd3947a52e88ae044e1 src/erasure-code/jerasure/gf-complete
>> -96c76b89d661c163f65a014b8042c9354ccf7f31 src/erasure-code/jerasure/jerasure
>> -51bf9cfacb644659e5d9c7e6fe66396726f2f4f4 src/fmt
>> -389cb68b87193358358ae87cc56d257fd0d80189 src/googletest
>> -4b36e413c9ac28b4757b297779470693b699aeae src/isa-l
>> -7ad60f7330a421fe2adcab1a2d3dbf4159af6bc2 src/jaegertracing/jaeger-client-cpp
>> -4bb431f7728eaf383a07e86f9754a5b67575dab0 src/jaegertracing/opentracing-cpp
>> -b75e88a33d67ae05ef9b5fa001d2a63a2effe377 src/jaegertracing/thrift
>> -b25cde94c9b8686988ed1236bd807afe74991333 src/libkmip
>> -0b46d500a741afabe5c4efd1bb07e6f8903f0ef0 src/pybind/mgr/rook/rook-client-python
>> -f54b0e47a08782a6131cc3d60f94d038fa6e0a51 src/rapidjson
>> -8ab4c1aa3f1c7d89077d7f81e7d457e8333a0430 src/rocksdb
>> -7ae7a12c138d4607d6c012228c06f3802c493c49 src/s3select
>> -afafbaa8d43627fffa00541ac26a31904d0268ab src/seastar
>> -9ee6d12f35ab2fa48b469f13b4830a5e5cfde45e src/spawn
>> -1a527e501f810e2b39b9862c96f3e8bdc465db80 src/spdk
>> -1f40c6511fa8dd9d2e337ca8c9bc18b3e87663c9 src/xxHash
>> -b706286adbba780006a47ef92df0ad7a785666b6 src/zstd
>>

PS D:\career\VDT\GD2\upgrade_Ceph\ceph16.2.5\ceph> git describe --tags --exact-match HEAD
v16.2.5
PS D:\career\VDT\GD2\upgrade_Ceph\ceph16.2.5\ceph> git submodule status --cached
-2d7d78b9cc52e8a9529d8cc2d2954c7d375d5dd7 ceph-erasure-code-corpus
-70228ed56466b4be8a9abff9024f69820f68f6d0 ceph-object-corpus
-f24ceec055ea236a093988237a9821d145f5f7c8 src/blkin
-fd6124c74da0801f23f9d324559d8b66fb83f533 src/c-ares
-bb99e93da00c3fe8c6b6a98520fb17cf64710ce7 src/civetweb
-603529a4e06ac8a1662c13d6b31f122e21830352 src/crypto/isa-l/isa-l_crypto
-9b1326cfa09735ae18b1c4c308ec424c5f1b9cce src/dmclock
-7e61b44404f0ed410c83cfd3947a52e88ae044e1 src/erasure-code/jerasure/gf-complete
-96c76b89d661c163f65a014b8042c9354ccf7f31 src/erasure-code/jerasure/jerasure
-51bf9cfacb644659e5d9c7e6fe66396726f2f4f4 src/fmt
-389cb68b87193358358ae87cc56d257fd0d80189 src/googletest
-806b55ee578efd8158962b90121a4568eb1ecb66 src/isa-l
-7ad60f7330a421fe2adcab1a2d3dbf4159af6bc2 src/jaegertracing/jaeger-client-cpp
-4bb431f7728eaf383a07e86f9754a5b67575dab0 src/jaegertracing/opentracing-cpp
-b75e88a33d67ae05ef9b5fa001d2a63a2effe377 src/jaegertracing/thrift
-b25cde94c9b8686988ed1236bd807afe74991333 src/libkmip
-0b46d500a741afabe5c4efd1bb07e6f8903f0ef0 src/pybind/mgr/rook/rook-client-python
-f54b0e47a08782a6131cc3d60f94d038fa6e0a51 src/rapidjson
-8ab4c1aa3f1c7d89077d7f81e7d457e8333a0430 src/rocksdb
-7ae7a12c138d4607d6c012228c06f3802c493c49 src/s3select
-afafbaa8d43627fffa00541ac26a31904d0268ab src/seastar
-9ee6d12f35ab2fa48b469f13b4830a5e5cfde45e src/spawn
-1a527e501f810e2b39b9862c96f3e8bdc465db80 src/spdk
-1f40c6511fa8dd9d2e337ca8c9bc18b3e87663c9 src/xxHash
-b706286adbba780006a47ef92df0ad7a785666b6 src/zstd



| Submodule                | `v16.2.5`               | `v16.2.15`              | Kết quả                |
| ------------------------ | ------------------------- | ------------------------- | ------------------------ |
| `src/isa-l`            | `806b55ee`              | `4b36e413`              | **Có thay đổi** |
| `src/rocksdb`          | `8ab4c1aa`              | `8ab4c1aa`              | Giữ nguyên             |
| Các submodule còn lại | Cùng hash giữa hai bản | Cùng hash giữa hai bản | Giữ nguyên             |

| Thay đổi                                    | Ý nghĩa                                                                                                                                                                                                                               |
| --------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `ldr x_const, =const_tbl`→`adrp`+`add` | Lấy địa chỉ bảng theo vị trí tương đối với mã chương trình, tránh địa chỉ tuyệt đối trong literal pool gây text relocation.[GNU assembler](https://sourceware.org/binutils/docs/as/AArch64_002dRelocations.html) |
| `.data`→`.rodata`                        | Chuyển bảng hằng sang vùng dữ liệu chỉ đọc; giá trị bảng giữ nguyên                                                                                                                                                       |
