#include <stdlib.h>

void release_conn_bad(struct conn *c) {
    /* the field is touched through a freed object */
    free(c->name);
    free(c);
    if (c->name != NULL) note("named");
}
