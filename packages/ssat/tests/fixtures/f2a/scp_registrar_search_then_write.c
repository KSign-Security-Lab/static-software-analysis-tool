#include <stddef.h>
#define MSG_SET_PROFILE 41

typedef int (*HandlerFn)(void *);

typedef struct {
    int action;
    HandlerFn handler;
} HandlerEntry;

static HandlerEntry table[2];

static int on_scp(void *payload) { return payload == NULL; }

/* search-then-write: the slot is located at runtime by COMPARING the action
 * (a predicate) inside a loop, then only the callback is stored. The id is
 * never co-stored with the callback into one statically-visible slot, so the
 * baseline paired-store extractor cannot establish the action->slot binding. */
static void register_handler(int action, HandlerFn fn) {
    for (int i = 0; i < 2; i++) {
        if (table[i].action == action) {
            table[i].handler = fn;
            return;
        }
    }
}

static void init(void) {
    table[0].action = MSG_SET_PROFILE;
    register_handler(MSG_SET_PROFILE, on_scp);
}
