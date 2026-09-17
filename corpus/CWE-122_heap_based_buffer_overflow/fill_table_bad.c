#include <stdlib.h>

void fill_table_bad(int n) {
    int *table = malloc((size_t)n * sizeof(int));
    for (int i = 0; i <= n; i++) table[i] = i;
    publish(table, n);
}
