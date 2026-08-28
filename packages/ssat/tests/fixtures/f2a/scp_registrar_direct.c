#include <stddef.h>
#define MSG_SET_PROFILE 41
typedef int (*HandlerFn)(void *);
typedef struct { int action; HandlerFn fn; } Reg;
static Reg g_table[8];
static int g_n = 0;
static int on_scp(void *payload) { return payload == NULL; }
/* registrar stores the params into a slot itself (depth 1) */
static void register_handler(int action, HandlerFn fn) {
    g_table[g_n].action = action;
    g_table[g_n].fn = fn;
    g_n++;
}
static void init(void) { register_handler(MSG_SET_PROFILE, on_scp); }
