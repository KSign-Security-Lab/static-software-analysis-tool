/*
 * Synthetic OCPP `DataTransfer` example for the F2-A KB entry
 * (DataTransfer.data -> database_query_execution / SQL injection).
 *   source : request->data   (vendor_controlled_payload, untrusted)
 *   flow   : data -> payload -> sql
 *   sink   : sqlite3_exec(db, sql, ...)   (database_query_execution)
 *   checks : none (no schema/length validation, no parameterized query)
 */
#include <string.h>
#include <stdio.h>

typedef struct sqlite3 sqlite3;
int sqlite3_exec(sqlite3 *db, const char *sql, int (*cb)(void *, int, char **, char **),
                 void *arg, char **errmsg);

typedef struct DataTransferReq {
    char *data;
} DataTransferReq;

void store_vendor_data(sqlite3 *db, const char *data) {
    char sql[512];
    sprintf(sql, "INSERT INTO vendor_log(payload) VALUES('%s')", data);  /* data -> sql */
    sqlite3_exec(db, sql, 0, 0, 0);                                       /* sink */
}

void handle_data_transfer(sqlite3 *db, DataTransferReq *request) {
    char *payload = request->data;     /* source binding */
    store_vendor_data(db, payload);
}

void dispatch(const char *action, sqlite3 *db, DataTransferReq *request) {
    if (strcmp(action, "DataTransfer") == 0)
        handle_data_transfer(db, request);
}
