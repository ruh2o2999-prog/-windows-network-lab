package org.example.reversefixture;
import android.app.Activity;
import android.os.Bundle;
import android.graphics.Color;
import android.view.Gravity;
import android.widget.TextView;
import android.util.Log;
import java.io.InputStream;
import java.net.URL;
import java.net.HttpURLConnection;
public final class MainActivity extends Activity {
  private TextView label;
  @Override public void onCreate(Bundle state) {
    super.onCreate(state);
    label = new TextView(this);
    label.setText("PUBLIC_FIXTURE_V11\nNETWORK_PENDING");
    label.setTextSize(20);
    label.setTextColor(Color.BLACK);
    label.setGravity(Gravity.CENTER);
    setContentView(label);
    new Thread(() -> {
      String example = check("https://example.com/");
      String github = check("https://api.github.com/");
      String result = "PUBLIC_FIXTURE_V11\nEXAMPLE_" + example + "\nGITHUB_" + github;
      Log.i("COLDBOOT_NET_V11",result.replace('\n',' '));
      runOnUiThread(() -> label.setText(result));
    }).start();
  }
  private String check(String address) {
    HttpURLConnection connection = null;
    try {
      connection = (HttpURLConnection) new URL(address).openConnection();
      connection.setConnectTimeout(13000);
      connection.setReadTimeout(13000);
      connection.setRequestMethod("GET");
      connection.setRequestProperty("User-Agent","android-coldboot-fixture-v1.1");
      int status = connection.getResponseCode();
      if (status>=200 && status<400) {
        try (InputStream in=connection.getInputStream()) { int b=in.read(); return b>=0 ? "HTTPS_OK" : "EMPTY_RESPONSE"; }
      }
      return "HTTP_"+status;
    } catch(Exception e) {
      return "FAIL_"+e.getClass().getSimpleName();
    } finally { if(connection!=null) connection.disconnect(); }
  }
}
