#include <stddef.h>
#define MSG_SET_PROFILE 41

typedef int (*HandlerFn)(void *);
typedef struct { int action; HandlerFn fn; } Reg;

static int store_profile(void *payload) { return payload == NULL; }            /* numeric registration (id 41) */
static int handle_set_charging_profile(void *payload) { return payload == NULL; } /* name-pattern match */

static Reg g_table[] = {
    { 41, store_profile }
};
