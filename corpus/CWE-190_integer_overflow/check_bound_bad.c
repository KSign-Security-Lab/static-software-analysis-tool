#include <stddef.h>

int check_bound_bad(int offset, int count) {
    if (offset + count > 4096) return -1;
    return offset + count;
}
