#include <iostream>
#include <vector>
#include <string>
#include <algorithm>
using namespace std;

const int N = 10010;
string s;
int n;
bool pal[N][N];

void precompute() {
    n = s.size();
    for (int i = 0; i < n; i++) {
        pal[i][i] = true;
        if (i < n - 1) pal[i][i+1] = (s[i] == s[i+1]);
    }
    for (int len = 3; len <= n; len++) {
        for (int i = 0; i + len - 1 < n; i++) {
            int j = i + len - 1;
            pal[i][j] = (s[i] == s[j] && pal[i+1][j-1]);
        }
    }
}

bool canMatch(int l1, int r1, int l2, int r2) {
    if (r1 - l1 != r2 - l2) return false;
    int len = r1 - l1 + 1;
    bool equal = true;
    for (int i = 0; i < len; i++) {
        if (s[l1 + i] != s[l2 + i]) {
            equal = false;
            break;
        }
    }
    if (equal) return true;
    bool reverse = true;
    for (int i = 0; i < len; i++) {
        if (s[l1 + i] != s[l2 + len - 1 - i]) {
            reverse = false;
            break;
        }
    }
    return reverse;
}

int solve(int l, int r, vector<vector<int>>& memo) {
    if (l >= r) return 0;
    if (memo[l][r] != -1) return memo[l][r];

    int res = 0;
    int len = r - l + 1;
    if (len % 2 == 0) {
        for (int k = 1; k <= len / 2; k++) {
            int l1 = l, r1 = l + k - 1;
            int l2 = r - k + 1, r2 = r;
            if (canMatch(l1, r1, l2, r2)) {
                if (k == len / 2) {
                    res = max(res, 2);
                } else {
                    int inner = solve(l + k, r - k, memo);
                    if (inner > 0) {
                        res = max(res, inner + 2);
                    }
                }
            }
        }
    } else {
        for (int k = 1; k <= len / 2; k++) {
            int l1 = l, r1 = l + k - 1;
            int l2 = r - k + 1, r2 = r;
            if (canMatch(l1, r1, l2, r2)) {
                if (k == len / 2) {
                    int mid = l + k;
                    if (pal[mid][mid]) {
                        res = max(res, 3);
                    }
                } else {
                    int inner = solve(l + k, r - k, memo);
                    if (inner > 0) {
                        res = max(res, inner + 2);
                    }
                }
            }
        }
    }
    memo[l][r] = res;
    return res;
}

int main() {
    cin >> s;
    n = s.size();
    vector<vector<int>> memo(n, vector<int>(n, -1));
    precompute();

    int maxParts = solve(0, n - 1, memo);
    if (maxParts < 2) {
        cout << "NO" << endl;
    } else {
        cout << "YES" << endl;
        cout << maxParts << endl;
    }
    return 0;
}