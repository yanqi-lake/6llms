#include <bits/stdc++.h>
using namespace std;

struct Fraction {
    long long num;  // 分子
    long long den;   // 分母
    
    Fraction(long long n = 0, long long d = 1) {
        if (d < 0) { n = -n; d = -d; }
        long long g = gcd(abs(n), d);
        num = n / g;
        den = d / g;
    }
    
    // 加法
    Fraction operator+(const Fraction& other) const {
        long long n = num * other.den + other.num * den;
        long long d = den * other.den;
        return Fraction(n, d);
    }
    
    // 乘法（乘以一个整数）
    Fraction operator*(long long k) const {
        return Fraction(num * k, den);
    }
    
    // 除法（除以一个整数）
    Fraction operator/(long long k) const {
        return Fraction(num, den * k);
    }
    
    // 打印
    void print() const {
        cout << num << " " << den << "\n";
    }
};

long long gcd(long long a, long long b) {
    return b == 0 ? a : gcd(b, a % b);
}

int main() {
    ios::sync_with_stdio(false);
    cin.tie(nullptr);
    
    int n, m;
    if (!(cin >> n >> m)) return 0;
    
    vector<vector<int>> adj(n + 1);      // 出边
    vector<int> inDegree(n + 1, 0);      // 入度
    vector<int> outDegree(n + 1, 0);     // 出度
    
    // 读入图
    for (int i = 1; i <= n; i++) {
        int d;
        cin >> d;
        outDegree[i] = d;
        for (int j = 0; j < d; j++) {
            int a;
            cin >> a;
            adj[i].push_back(a);
            inDegree[a]++;
        }
    }
    
    // 使用队列进行拓扑排序
    queue<int> q;
    vector<Fraction> water(n + 1, Fraction(0, 1));  // 每个节点收到的水量
    
    // 初始：m个接收口各收到1吨水
    for (int i = 1; i <= m; i++) {
        if (inDegree[i] == 0) {  // 入度为0的节点是接收口
            water[i] = Fraction(1, 1);
            q.push(i);
        }
    }
    
    // 拓扑排序
    while (!q.empty()) {
        int u = q.front();
        q.pop();
        
        if (outDegree[u] == 0) continue;  // 最终排水口不再流出
        
        // 将u的水均分到所有出边
        Fraction each = water[u] / outDegree[u];
        for (int v : adj[u]) {
            water[v] = water[v] + each;
            inDegree[v]--;
            if (inDegree[v] == 0) {
                q.push(v);
            }
        }
    }
    
    // 输出所有最终排水口（出度为0的节点）
    vector<int> finals;
    for (int i = 1; i <= n; i++) {
        if (outDegree[i] == 0) {
            finals.push_back(i);
        }
    }
    sort(finals.begin(), finals.end());
    
    for (int v : finals) {
        water[v].print();
    }
    
    return 0;
}
