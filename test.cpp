#include <iostream>
#include <vector>
using namespace std;

struct Carpet {
    int a, b, g, k;
};

int main() {
    int n;
    if (!(cin >> n)) return 0;
    
    vector<Carpet> carpets(n + 1);
    
    for (int i = 1; i <= n; i++) {
        cin >> carpets[i].a >> carpets[i].b >> carpets[i].g >> carpets[i].k;
    }
    
    int x, y;
    cin >> x >> y;
    
    int result = -1;
    for (int i = n; i >= 1; i--) {
        if (x >= carpets[i].a && x <= carpets[i].a + carpets[i].g && 
            y >= carpets[i].b && y <= carpets[i].b + carpets[i].k) {
            result = i;
            break;
        }
    }
    
    cout << result << endl;
    
    return 0;
}