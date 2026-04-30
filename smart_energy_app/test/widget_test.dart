// This is a basic Flutter widget test.
//
// To perform an interaction with a widget in your test, use the WidgetTester
// utility in the flutter_test package. For example, you can send tap and scroll
// gestures. You can also use WidgetTester to find child widgets in the widget
// tree, read text, and verify that the values of widget properties are correct.

import 'package:flutter_test/flutter_test.dart';

import 'package:smart_energy_app/main.dart';

void main() {
  testWidgets('Home screen displays app name', (WidgetTester tester) async {
    // Build our app and trigger a frame.
    await tester.pumpWidget(const SmartEnergyApp(enableRealtimeSync: false));

    // Verify that the app name is displayed.
    expect(find.text('Smart Energy Control'), findsOneWidget);

    // Verify that energy overview section exists.
    expect(find.text('Energy Overview'), findsOneWidget);
  });
}
