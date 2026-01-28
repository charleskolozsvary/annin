from texpdfedits.prompt import categorizeMarks

def testCategorize():
    test_markids = {
        0:['document0;0'],
        1:['document0;0', 'document0;1', 'document0;2'],
        2:['document0;0,footnote0;0'],
        3:['document0;0,footnote0;0', 'document0;0,footnote0;1'],
        4:['document0;0,footnote0;0', 'document0;0,footnote1;0'],
        5:['document0;0,footnote0;0', 'document0;1,footnote1;0'],
        6:['document0;0,footnote0;0', 'document0;1,footnote0;0'],
        7:['document0;0,footnote0;0', 'document0;0,footnote0;1', 'document0;0,footnote1;0'],
        8:['thanks0;0', 'thanks0;1', 'thanks0;2', 'thanks1;0', 'thanks1;1'],
        9:['title0;0', 'commby0;0'],
        10:['document10;5,caption3;0', 'document10;5,caption3;1', 'document10;5,caption3;1,footnote5;0']
    }
    answers = {
        0: 'compatible',
        1: 'compatible',
        2: 'compatible',
        3: 'compatible',
        4: 'almost compatible',
        5: 'incompatible',
        6: 'incompatible',
        7: 'almost compatible',
        8: 'almost compatible',
        9: 'incompatible',
        10: 'incompatible',
    }

    for test, m_ids in test_markids.items():
        assert answers[test] == categorizeMarks(m_ids)

if __name__ == '__main__':
    testCategorize()
                    
