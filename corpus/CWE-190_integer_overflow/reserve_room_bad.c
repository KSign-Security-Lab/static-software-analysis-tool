#include <stdlib.h>

void *reserve_room_bad(int len) {
    /* len + 1 wraps to a negative or tiny value at INT_MAX */
    return malloc(len + 1);
}
