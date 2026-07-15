#include <stddef.h>

typedef struct { int action; void *payload; } OcppFrame;
typedef enum { ACTION_BOOT = 1, ACTION_DATA_TRANSFER = 6 } OcppAction;
typedef int (*HandlerFn)(void *);
typedef struct { int action; HandlerFn fn; } Reg;

static int foo(void *payload) { return payload == NULL; }   /* registration target */
static int bar(void *payload) { return payload == NULL; }   /* switch target       */

static Reg g_table[] = {
    { ACTION_DATA_TRANSFER, foo }
};

static int dispatch(const OcppFrame *f) {
    switch (f->action) {
        case ACTION_DATA_TRANSFER:
            return bar(f->payload);
        default:
            return -1;
    }
}
