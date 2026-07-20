/* Field-order independence + multiple designated entries in one array:
 *  - RemoteStartTransaction: callback field BEFORE action field
 *  - DataTransfer:           action field BEFORE callback field */
typedef int (*HandlerFn)(void *);
typedef struct { int action; HandlerFn fn; } Reg;
typedef enum { ACTION_REMOTE_START = 3, ACTION_DATA_TRANSFER = 6 } OcppAction;
static int remote_handler(void *payload) { return payload == NULL; }
static int data_handler(void *payload) { return payload == NULL; }
static Reg handlers[] = {
    { .fn = remote_handler, .action = ACTION_REMOTE_START },
    { .action = ACTION_DATA_TRANSFER, .fn = data_handler },
};
