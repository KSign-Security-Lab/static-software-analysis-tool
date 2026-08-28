#include <sqlite3.h>
#include <string.h>

typedef enum {
    ACTION_BOOT_NOTIFICATION = 1,
    ACTION_DATA_TRANSFER = 7,
    ACTION_HEARTBEAT = 9
} OcppAction;

typedef struct {
    const char *vendor_id;
    const char *message_id;
    const char *data;
} DataTransferRequest;

typedef struct {
    OcppAction action;
    void *payload;
} OcppMessage;

static sqlite3 *g_database = NULL;

static int insert_diagnostic_record(sqlite3 *database, const char *diagnostic_payload) {
    char query[2048];
    snprintf(query, sizeof(query), "INSERT INTO diagnostic_events(payload) VALUES('%s');", diagnostic_payload);
    return sqlite3_exec(database, query, NULL, NULL, NULL);
}

static int handle_data_transfer(const DataTransferRequest *request) {
    const char *payload = request->data;
    return insert_diagnostic_record(g_database, payload);
}

static int dispatch_ocpp_message(const OcppMessage *message) {
    switch (message->action) {
        case ACTION_DATA_TRANSFER:
            return handle_data_transfer((const DataTransferRequest *)message->payload);
        default:
            return -1;
    }
}
