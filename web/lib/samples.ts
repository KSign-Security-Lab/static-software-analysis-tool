// Sample sources for the testing web. These mirror the F2-A test fixtures.

export interface Sample {
  id: string;
  label: string;
  language: string;
  filename: string;
  description: string;
  source: string;
}

export const SAMPLES: Sample[] = [
  {
    id: "update_firmware",
    label: "OCPP UpdateFirmware → system() (취약)",
    language: "c",
    filename: "update_firmware.c",
    description:
      "덱 예제: req->location 이 null 검사만 거쳐 system(cmd) 로 흘러갑니다.",
    source: `#include <string.h>
#include <stdlib.h>
#include <stdio.h>

typedef struct Request { char *location; } Request;

void download_firmware(const char *url) {
    char cmd[256];
    sprintf(cmd, "wget %s -O /tmp/fw.bin", url);
    system(cmd);
}

void handle_update_firmware(Request *req) {
    char *firmware_url = req->location;
    if (firmware_url == NULL) return;
    download_firmware(firmware_url);
}

void dispatch(const char *action, Request *req) {
    if (strcmp(action, "UpdateFirmware") == 0)
        handle_update_firmware(req);
}
`,
  },
  {
    id: "update_firmware_checked",
    label: "UpdateFirmware — scheme + signature 검사 포함",
    language: "c",
    filename: "update_firmware_checked.c",
    description:
      "strncmp(https) + verify_signature() 추가 — F2-A가 이를 충족(SATISFIED)으로 표시해야 합니다.",
    source: `#include <string.h>
#include <stdlib.h>
#include <stdio.h>

typedef struct Request { char *location; } Request;

int verify_signature(const char *path);

void download_firmware(const char *url) {
    char cmd[256];
    sprintf(cmd, "wget %s -O /tmp/fw.bin", url);
    system(cmd);
}

void handle_update_firmware(Request *req) {
    char *firmware_url = req->location;
    if (firmware_url == NULL) return;
    if (strncmp(firmware_url, "https://", 8) != 0) return;
    if (!verify_signature(firmware_url)) return;
    download_firmware(firmware_url);
}

void dispatch(const char *action, Request *req) {
    if (strcmp(action, "UpdateFirmware") == 0)
        handle_update_firmware(req);
}
`,
  },
  {
    id: "data_transfer",
    label: "OCPP DataTransfer → sqlite3_exec (SQL 인젝션)",
    language: "c",
    filename: "data_transfer.c",
    description:
      "벤더 페이로드 request->data 가 검증 없이 SQL 문자열로 이어져 sqlite3_exec 로 흘러갑니다.",
    source: `#include <string.h>
#include <stdio.h>

typedef struct sqlite3 sqlite3;
int sqlite3_exec(sqlite3 *db, const char *sql, int (*cb)(void *, int, char **, char **),
                 void *arg, char **errmsg);

typedef struct DataTransferReq {
    char *data;
} DataTransferReq;

void store_vendor_data(sqlite3 *db, const char *data) {
    char sql[512];
    sprintf(sql, "INSERT INTO vendor_log(payload) VALUES('%s')", data);
    sqlite3_exec(db, sql, 0, 0, 0);
}

void handle_data_transfer(sqlite3 *db, DataTransferReq *request) {
    char *payload = request->data;
    store_vendor_data(db, payload);
}

void dispatch(const char *action, sqlite3 *db, DataTransferReq *request) {
    if (strcmp(action, "DataTransfer") == 0)
        handle_data_transfer(db, request);
}
`,
  },
];
