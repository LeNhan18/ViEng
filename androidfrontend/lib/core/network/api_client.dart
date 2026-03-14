import 'package:dio/dio.dart';

/// Base URL: điện thoại thật dùng IP máy chạy backend (172.20.10.2). Emulator dùng 10.0.2.2:8000
const String kBaseUrl = 'http://172.20.10.2:8000/api/v1';

final Dio apiClient = Dio(BaseOptions(
  baseUrl: kBaseUrl,
  connectTimeout: const Duration(seconds: 30),
  receiveTimeout: const Duration(seconds: 60),
  headers: {'Content-Type': 'application/json', 'Accept': 'application/json'},
));
