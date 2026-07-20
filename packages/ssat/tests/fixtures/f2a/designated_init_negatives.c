/* Must remain NO_EVIDENCE / not classified as a handler registration:
 *  - g_partial: an incomplete entry with only the callback (no action field)
 *  - g_log:     an unrelated designated struct with a function-pointer field */
typedef int (*HandlerFn)(void *);
typedef struct { int action; HandlerFn fn; } Reg;
typedef enum { ACTION_REMOTE_START = 3 } OcppAction;
static int lonely_handler(void *payload) { return payload == NULL; }
static void log_sink(void *msg) { (void)msg; }
typedef struct { const char *name; void (*cb)(void *); } LogCfg;
static Reg g_partial[] = {
    { .fn = lonely_handler }
};
static LogCfg g_log = {
    .name = "logger", .cb = log_sink
};
